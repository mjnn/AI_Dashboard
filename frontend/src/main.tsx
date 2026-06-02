import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ChartThemeProvider } from "./context/ChartThemeContext";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ChartThemeProvider>
      <App />
    </ChartThemeProvider>
  </React.StrictMode>
);
