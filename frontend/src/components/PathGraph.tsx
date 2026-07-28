/**
 * DAG 路径图可视化
 */

import React, { useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { Tag, Typography } from "antd";
import { BuildOutlined } from "@ant-design/icons";
import type { KnowledgeNode, PathGraphData } from "@/types";

import "@xyflow/react/dist/style.css";

const { Text } = Typography;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 92;

function getNodeStyle(node: KnowledgeNode) {
  const base = {
    borderRadius: 16,
    border: "1px solid rgba(15, 118, 110, 0.15)",
    background: "linear-gradient(180deg, #fff, #f8fffe)",
    boxShadow: "0 10px 26px rgba(15, 23, 42, 0.06)",
    padding: 14,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
  } as const;

  if (node.status === "mastered") {
    return { ...base, borderColor: "rgba(5, 150, 105, 0.45)" };
  }
  if (node.status === "in_progress") {
    return { ...base, borderColor: "rgba(14, 116, 144, 0.5)" };
  }
  return base;
}

function layoutGraph(data: PathGraphData) {
  const nodes: Node[] = data.nodes.map((node, index) => ({
    id: node.id,
    type: "default",
    position: { x: index * (NODE_WIDTH + 48), y: 0 },
    data: { node },
    style: getNodeStyle(node),
  }));

  const edges: Edge[] = data.edges.map((edge) => ({
    id: `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#14b8a6", strokeWidth: 1.8 },
  }));

  return { nodes, edges };
}

const CustomNode: React.FC<{ data: { node: KnowledgeNode } }> = ({ data }) => {
  const { node } = data;
  return (
    <div className="path-node">
      <div className="path-node__head">
        <Tag color={node.status === "mastered" ? "green" : node.status === "in_progress" ? "cyan" : "default"}>
          {node.status}
        </Tag>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {node.estimated_minutes} min
        </Text>
      </div>
      <div className="path-node__title">{node.title}</div>
      <div className="path-node__desc">{node.description || "暂无说明"}</div>
    </div>
  );
};

interface PathGraphProps {
  data: PathGraphData;
}

const nodeTypes = { default: CustomNode };

const PathGraph: React.FC<PathGraphProps> = ({ data }) => {
  const flow = useMemo(() => layoutGraph(data), [data]);

  if (data.nodes.length === 0) {
    return (
      <div className="path-graph__empty">
        <BuildOutlined />
        <Text type="secondary">暂无知识图谱数据</Text>
      </div>
    );
  }

  return (
    <div className="path-graph">
      <ReactFlow
        nodes={flow.nodes}
        edges={flow.edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={18} color="rgba(15, 118, 110, 0.08)" />
        <MiniMap zoomable pannable />
        <Controls position="bottom-right" showInteractive={false} />
      </ReactFlow>
    </div>
  );
};

export default PathGraph;
