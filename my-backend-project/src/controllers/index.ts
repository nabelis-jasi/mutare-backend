class IndexController {
    public async getIndex(req: Request, res: Response): Promise<Response> {
        return res.status(200).json({ message: "Welcome to the API!" });
    }

    public async getHealth(req: Request, res: Response): Promise<Response> {
        return res.status(200).json({ status: "OK" });
    }
}

export default IndexController;