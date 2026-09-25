import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "katex/dist/katex.min.css";
import "react-mosaic-component/react-mosaic-component.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
