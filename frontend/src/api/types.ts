export type NodeType =
  | "thought"
  | "bet"
  | "task"
  | "decision"
  | "conflict"
  | "outcome"
  | "agent_firing"
  | "code_change"
  | "conversation"
  | "doc"
  | "gate_item"
  | "agent";

interface NodeBase {
  id: string;
  created_at: string;
  embedding_id?: string | null;
}

export interface ThoughtNode extends NodeBase {
  node_type: "thought";
  content: string;
  source: string;
  metadata: Record<string, unknown>;
}

export interface BetNode extends NodeBase {
  node_type: "bet";
  slug: string;
  title: string;
  vault_path: string;
  owner: string;
  horizon: string;
  confidence: string;
}

export interface TaskNode extends NodeBase {
  node_type: "task";
  linear_id: string;
  title: string;
  status: string;
}

export interface DecisionNode extends NodeBase {
  node_type: "decision";
  content: string;
  decided_by: string;
  reasoning: string;
}

export interface ConflictNode extends NodeBase {
  node_type: "conflict";
  summary: string;
  severity: string;
}

export interface OutcomeNode extends NodeBase {
  node_type: "outcome";
  summary: string;
  success: boolean;
}

export interface AgentFiringNode extends NodeBase {
  node_type: "agent_firing";
  agent_id: string;
  trace_id: string;
  started_at: string;
  completed_at: string | null;
  outcome: string | null;
}

export interface CodeChangeNode extends NodeBase {
  node_type: "code_change";
  repo: string;
  sha: string;
  summary: string;
}

export interface ConversationNode extends NodeBase {
  node_type: "conversation";
  summary: string;
  vault_path: string | null;
}

export interface DocNode extends NodeBase {
  node_type: "doc";
  vault_path: string;
  title: string;
}

export interface GateItemNode extends NodeBase {
  node_type: "gate_item";
  prompt: string;
  urgency: string;
  resolved_at: string | null;
  decision: string | null;
  reasoning: string;
}

export interface AgentNode extends NodeBase {
  node_type: "agent";
  role: string;
  persona: string;
  state: string;
  current_firing: string | null;
  last_active: string | null;
  enabled: boolean;
}

export type AnyNode =
  | ThoughtNode
  | BetNode
  | TaskNode
  | DecisionNode
  | ConflictNode
  | OutcomeNode
  | AgentFiringNode
  | CodeChangeNode
  | ConversationNode
  | DocNode
  | GateItemNode
  | AgentNode;

export interface Edge {
  from_id: string;
  from_type: NodeType | null;
  to_id: string;
  to_type: NodeType | null;
  edge_type: string;
  created_at: string;
  confidence: number;
}

export interface GraphState {
  nodes: AnyNode[];
  edges: Edge[];
}

export interface GraphChangedEvent {
  event: "graph.changed";
  change_type: "node_created" | "node_updated" | "edge_created";
  node_id?: string | null;
  edge_id?: string | null;
}

export interface GateItemCreatedEvent {
  event: "gate.created";
  gate_item_id: string;
  thought_id: string;
  urgency: string;
}

export interface FireNeuronEvent {
  event: "fire.neuron";
  thought_id: string;
  agent_role: string;
  task_summary: string;
}

export type StreamEvent =
  | GraphChangedEvent
  | GateItemCreatedEvent
  | FireNeuronEvent;
