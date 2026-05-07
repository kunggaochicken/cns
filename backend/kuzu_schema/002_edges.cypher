// Generic edge type — body holds the edge type so we get one table for all relationships
CREATE REL TABLE IF NOT EXISTS REL(
  FROM Thought TO Thought, FROM Thought TO Bet, FROM Thought TO Task,
  FROM Thought TO Decision, FROM Thought TO Conflict, FROM Thought TO Outcome,
  FROM Thought TO AgentFiring, FROM Thought TO CodeChange, FROM Thought TO Conversation,
  FROM Thought TO Doc, FROM Thought TO GateItem, FROM Thought TO Agent,
  FROM Bet TO Thought, FROM Bet TO Bet, FROM Bet TO Task,
  FROM Bet TO Decision, FROM Bet TO Conflict, FROM Bet TO Outcome,
  FROM Bet TO AgentFiring, FROM Bet TO CodeChange, FROM Bet TO Doc,
  FROM Bet TO GateItem,
  FROM AgentFiring TO Thought, FROM AgentFiring TO Bet, FROM AgentFiring TO Task,
  FROM AgentFiring TO Decision, FROM AgentFiring TO CodeChange,
  FROM AgentFiring TO Doc, FROM AgentFiring TO Outcome,
  FROM GateItem TO AgentFiring, FROM GateItem TO Decision, FROM GateItem TO Bet,
  FROM Decision TO GateItem, FROM Decision TO Bet, FROM Decision TO Outcome,
  FROM Conflict TO Bet, FROM Conflict TO GateItem,
  FROM Agent TO AgentFiring,
  edge_type STRING,
  created_at TIMESTAMP,
  confidence DOUBLE
);
