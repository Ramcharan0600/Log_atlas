import "dotenv/config";
import mongoose from "mongoose";
import { app } from "./app.js";

const PORT = process.env.PORT || 8000;
await mongoose.connect(process.env.MONGO_URI || "mongodb://localhost:27017/logmind");
app.listen(PORT, () => console.log(`LogMind API on http://localhost:${PORT}/api`));
