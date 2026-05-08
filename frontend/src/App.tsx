import BrainView from "./views/BrainView";
import { GraphProvider } from "./state/GraphProvider";

export default function App() {
  return (
    <GraphProvider>
      <BrainView />
    </GraphProvider>
  );
}
