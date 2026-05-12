import { useEffect } from 'react';

export default function CameraGraphPanel({ graph, onLoad }) {
  useEffect(() => {
    if (!graph && onLoad) onLoad();
  }, [graph, onLoad]);

  if (!graph) return <div className="text-xs text-gray-400">Loading camera graph…</div>;

  return (
    <div className="text-xs">
      <div className="mb-2 font-semibold text-gray-700">
        Camera Graph — {graph.node_count} nodes, {graph.edge_count} edges
      </div>
      <ul className="max-h-48 overflow-y-auto divide-y divide-gray-100">
        {(graph.nodes || []).map((n) => (
          <li key={n.camera_id} className="py-1 text-gray-600">
            <span className="font-medium">{n.name || n.camera_id}</span>
            <span className="ml-2 text-gray-400">
              ({n.latitude?.toFixed(4)}, {n.longitude?.toFixed(4)})
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
