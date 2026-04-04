import { DataFlowDiagram } from "../components/dataflow/DataFlowDiagram";

export function DataFlow() {

  return (
    <div className="flex flex-col h-[calc(100dvh-theme(spacing.14))] md:h-dvh -m-2 sm:-m-4 md:-m-8">
      <DataFlowDiagram />
    </div>
  );
}
