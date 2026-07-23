import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// 引入 Ant Design 的全局样式
// What: Ant Design 组件库的默认 CSS 样式
// Why: 确保所有 Antd 组件的样式正确生效，避免样式缺失导致布局异常
import "antd/dist/reset.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
