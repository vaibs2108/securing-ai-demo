import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { LoadingBlock } from "../components/ui";
import { AssetGraph } from "../components/AssetGraph";

export function AssetGraphPage() {
  const { data, isLoading } = useQuery({ queryKey: ["asset-graph"], queryFn: api.assetGraph, staleTime: 15_000 });

  if (isLoading || !data) return <LoadingBlock label="Assembling the real asset graph…" />;

  return (
    <div>
      <div className="hero-banner">
        <div className="hero-title">AI Asset &amp; Risk Graph</div>
        <div className="hero-subtitle">
          Every real entity currently flowing through the pipeline — the target agent, its models, its access, its
          findings, and every governance rule's real decision about it — in one connective view.
        </div>
      </div>
      <AssetGraph data={data} />
    </div>
  );
}
