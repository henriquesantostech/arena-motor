import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./styles.css";
import { createRoot } from "react-dom/client";
import App from "./App";

performance.mark("arena:app");
createRoot(document.getElementById("root")!).render(<App />);
