# routes/reportprocessor_routes.py

from flask import Blueprint, request, jsonify
from datetime import datetime
import re
from config import get_db, extract_vehicles_from_text, extract_complaints

reportprocessor_bp = Blueprint('reportprocessor', __name__)

@reportprocessor_bp.route('/api/process_report', methods=['POST'])
def process_report():
    try:
        data = request.json
        report_text = data.get('report_text', '')
        
        date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', report_text)
        report_date = date_match.group(1) if date_match else datetime.now().strftime('%d/%m/%Y')
        
        complaints_match = re.search(r'Complaints received[=:\s]*(\d+)', report_text, re.IGNORECASE)
        total_complaints = int(complaints_match.group(1)) if complaints_match else 0
        
        attended_match = re.search(r'attended to[=:\s]*(\d+)', report_text, re.IGNORECASE)
        attended_to = int(attended_match.group(1)) if attended_match else 0
        
        operational_vehicles, workshop_vehicles = extract_vehicles_from_text(report_text)
        complaints = extract_complaints(report_text)
        
        return jsonify({
            "success": True,
            "report_date": report_date,
            "total_complaints": total_complaints,
            "attended_to": attended_to,
            "outstanding_jobs": total_complaints - attended_to,
            "parsed_complaints_count": len(complaints),
            "operational_vehicles_count": len(operational_vehicles),
            "workshop_vehicles_count": len(workshop_vehicles),
            "operational_vehicles": operational_vehicles,
            "workshop_vehicles": workshop_vehicles,
            "complaints": complaints
        })
    except Exception as e:
        print(f"Error in /api/process_report: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@reportprocessor_bp.route('/api/update_asset_status', methods=['POST'])
def update_asset_status():
    """Update manhole and pipeline status based on complaint buffer zones"""
    try:
        data = request.json
        complaints = data.get('complaints', [])
        
        conn = get_db()
        if conn is None:
            return jsonify({"success": False, "error": "Database connection failed"}), 500
        
        cur = conn.cursor()
        
        updated_manholes = []
        updated_pipelines = []
        
        # Expanded keywords for better detection
        pending_keywords = [
            'waiting', 'work in progress', 'in progress', 'pending', 
            'from the previous days', 'referred', 'partial', 'partial blockage',
            'silt', 'debris', 'slow flow', 'reduced flow', 'maintenance required'
        ]
        critical_keywords = [
            'urgent', 'critical', 'burst', 'damaged', 'broken', 
            'blocked', 'referred to tender', 'complete blockage', 
            'overflow', 'spillage', 'emergency', 'flooding'
        ]
        
        for complaint in complaints:
            if complaint.get('latitude') and complaint.get('longitude'):
                lat = complaint['latitude']
                lng = complaint['longitude']
                buffer_radius_meters = complaint.get('buffer_radius', 200)  # Increased default buffer
                text_lower = complaint.get('original_text', '').lower()
                address = complaint.get('address', '').lower()
                
                # Combine text for better keyword matching
                combined_text = text_lower + " " + address
                
                # Determine status based on complaint text
                if any(keyword in combined_text for keyword in critical_keywords):
                    asset_status = 'critical'
                    status_color = 'red'
                elif any(keyword in combined_text for keyword in pending_keywords):
                    asset_status = 'warning'
                    status_color = 'orange'
                else:
                    asset_status = 'warning'  # Default to warning for any complaint
                    status_color = 'orange'
                
                print(f"\n{'='*50}")
                print(f"Processing complaint: {complaint.get('address')}")
                print(f"  Location: ({lat}, {lng})")
                print(f"  Buffer radius: {buffer_radius_meters}m")
                print(f"  Detected status: {asset_status} ({status_color})")
                print(f"  Complaint text: {complaint.get('original_text', '')[:100]}...")
                
                # FIRST: Check how many manholes are within buffer (for debugging)
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM waste_water_manhole 
                    WHERE ST_DWithin(
                        geom::geography, 
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 
                        %s
                    )
                """, (lng, lat, buffer_radius_meters))
                nearby_count = cur.fetchone()['count']
                print(f"  Found {nearby_count} manholes within {buffer_radius_meters}m buffer")
                
                # Update manholes within buffer
                cur.execute("""
                    UPDATE waste_water_manhole 
                    SET bloc_stat = %s,
                        last_mod = NOW()
                    WHERE ST_DWithin(
                        geom::geography, 
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 
                        %s
                    )
                    AND (bloc_stat IS NULL OR bloc_stat NOT IN ('critical'))
                    RETURNING manhole_id, suburb_nam
                """, (asset_status, lng, lat, buffer_radius_meters))
                
                manhole_rows = cur.fetchall()
                for row in manhole_rows:
                    updated_manholes.append(row['manhole_id'])
                    print(f"  → UPDATED Manhole {row['manhole_id']} in {row['suburb_nam']} to {asset_status}")
                
                # Check pipelines within buffer
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM waste_water_pipeline 
                    WHERE ST_DWithin(
                        geom::geography, 
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 
                        %s
                    )
                """, (lng, lat, buffer_radius_meters))
                nearby_pipes = cur.fetchone()['count']
                print(f"  Found {nearby_pipes} pipelines within {buffer_radius_meters}m buffer")
                
                # Update pipelines within buffer
                cur.execute("""
                    UPDATE waste_water_pipeline 
                    SET block_stat = %s,
                        last_mod = NOW()
                    WHERE ST_DWithin(
                        geom::geography, 
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, 
                        %s
                    )
                    AND (block_stat IS NULL OR block_stat NOT IN ('critical'))
                    RETURNING pipe_id
                """, (asset_status, lng, lat, buffer_radius_meters))
                
                pipeline_rows = cur.fetchall()
                for row in pipeline_rows:
                    updated_pipelines.append(row['pipe_id'])
                    print(f"  → UPDATED Pipeline {row['pipe_id']} to {asset_status}")
                
                if len(manhole_rows) == 0 and len(pipeline_rows) == 0:
                    print(f"  ⚠️ WARNING: No assets found within {buffer_radius_meters}m buffer!")
                    print(f"  Consider increasing buffer radius for this complaint")
        
        conn.commit()
        cur.close()
        conn.close()
        
        unique_manholes = list(set(updated_manholes))
        unique_pipelines = list(set(updated_pipelines))
        
        print(f"\n{'='*50}")
        print(f"TOTAL UPDATED: {len(unique_manholes)} manholes, {len(unique_pipelines)} pipelines")
        print(f"{'='*50}\n")
        
        return jsonify({
            "success": True,
            "updated_manholes": len(unique_manholes),
            "updated_pipelines": len(unique_pipelines),
            "message": f"Updated {len(unique_manholes)} manholes and {len(unique_pipelines)} pipelines",
            "details": {
                "manhole_ids": unique_manholes[:20],  # First 20 for debugging
                "pipeline_ids": unique_pipelines[:20]
            }
        })
    except Exception as e:
        print(f"Error in update_asset_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@reportprocessor_bp.route('/api/reset_asset_status', methods=['POST'])
def reset_asset_status():
    """Reset all manholes and pipelines to normal (good) status"""
    try:
        conn = get_db()
        if conn is None:
            return jsonify({"success": False, "error": "Database connection failed"}), 500
        
        cur = conn.cursor()
        
        # Count before reset
        cur.execute("SELECT COUNT(*) FROM waste_water_manhole WHERE bloc_stat IN ('warning', 'pending', 'critical')")
        manholes_to_reset = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(*) FROM waste_water_pipeline WHERE block_stat IN ('warning', 'pending', 'critical')")
        pipelines_to_reset = cur.fetchone()['count']
        
        # Reset manholes to good status
        cur.execute("""
            UPDATE waste_water_manhole 
            SET bloc_stat = 'good',
                last_mod = NOW()
            WHERE bloc_stat IN ('warning', 'pending', 'critical')
        """)
        manholes_reset = cur.rowcount
        
        # Reset pipelines to good status
        cur.execute("""
            UPDATE waste_water_pipeline 
            SET block_stat = 'good',
                last_mod = NOW()
            WHERE block_stat IN ('warning', 'pending', 'critical')
        """)
        pipelines_reset = cur.rowcount
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"Reset: {manholes_reset} manholes, {pipelines_reset} pipelines")
        
        return jsonify({
            "success": True,
            "manholes_reset": manholes_reset,
            "pipelines_reset": pipelines_reset,
            "message": f"Reset {manholes_reset} manholes and {pipelines_reset} pipelines to normal"
        })
    except Exception as e:
        print(f"Error in reset_asset_status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500