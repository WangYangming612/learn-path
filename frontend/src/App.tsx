import React from "react";
import { Layout, Typography, Space } from "antd";

const { Content } = Layout;
const { Title, Paragraph } = Typography;

/**
 * 根组件 — 欢迎页
 *
 * What: 应用的入口组件，渲染欢迎页面
 * Why: 作为 Step 1 骨架验证，展示核心品牌信息和项目口号
 *      后续步骤将在此基础上升级为路由系统
 */
const App: React.FC = () => {
  return (
    <Layout
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      <Content style={{ textAlign: "center", padding: "0 24px" }}>
        <Space direction="vertical" size="large">
          <Title
            level={1}
            style={{
              color: "#fff",
              fontSize: "2.8rem",
              margin: 0,
              letterSpacing: "2px",
            }}
          >
            LearnPath - 个性化学习路径系统
          </Title>
          <Paragraph
            style={{
              color: "rgba(255, 255, 255, 0.85)",
              fontSize: "1.2rem",
              margin: 0,
            }}
          >
            你只管学，剩下的交给我
          </Paragraph>
        </Space>
      </Content>
    </Layout>
  );
};

export default App;
