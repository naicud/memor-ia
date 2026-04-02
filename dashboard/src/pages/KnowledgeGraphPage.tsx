import { useRef, useEffect, useCallback, useState } from 'react';
import { api } from '@/lib/api';
import { useAsync } from '@/hooks/useAsync';
import { Section, Spinner, ErrorDisplay, EmptyState } from '@/components/ui';
import { Network, RefreshCw } from 'lucide-react';
import type { GraphData, GraphNode, GraphEdge } from '@/types/api';

interface CanvasNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  color: string;
}

const TYPE_COLORS: Record<string, string> = {
  namespace: '#5c7cfa',
  memory: '#748ffc',
  entity: '#91a7ff',
  concept: '#f59e0b',
  default: '#6b7280',
};

export function KnowledgeGraphPage() {
  const graphResult = useAsync(() => api.graph(), []);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredNode, setHoveredNode] = useState<CanvasNode | null>(null);

  const draw = useCallback(
    (graphData: GraphData) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const rect = canvas.parentElement!.getBoundingClientRect();
      canvas.width = rect.width;
      canvas.height = rect.height;
      const W = canvas.width;
      const H = canvas.height;

      // Initialize nodes with positions
      const nodes: CanvasNode[] = graphData.nodes.map((n, i) => ({
        ...n,
        x: W / 2 + (Math.cos((i / graphData.nodes.length) * Math.PI * 2) * W) / 3,
        y: H / 2 + (Math.sin((i / graphData.nodes.length) * Math.PI * 2) * H) / 3,
        vx: 0,
        vy: 0,
        color: TYPE_COLORS[n.type] || TYPE_COLORS.default,
      }));

      const nodeMap = new Map(nodes.map((n) => [n.id, n]));

      // Force-directed simulation
      const simulate = () => {
        const k = 0.01;
        const repulsion = 5000;

        // Repulsion between all nodes
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const dx = nodes[j].x - nodes[i].x;
            const dy = nodes[j].y - nodes[i].y;
            const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
            const f = repulsion / (dist * dist);
            const fx = (dx / dist) * f;
            const fy = (dy / dist) * f;
            nodes[i].vx -= fx;
            nodes[i].vy -= fy;
            nodes[j].vx += fx;
            nodes[j].vy += fy;
          }
        }

        // Attraction along edges
        graphData.edges.forEach((edge: GraphEdge) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return;
          const dx = target.x - source.x;
          const dy = target.y - source.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const f = k * (dist - 120);
          const fx = (dx / (dist || 1)) * f;
          const fy = (dy / (dist || 1)) * f;
          source.vx += fx;
          source.vy += fy;
          target.vx -= fx;
          target.vy -= fy;
        });

        // Center gravity
        nodes.forEach((n) => {
          n.vx += (W / 2 - n.x) * 0.001;
          n.vy += (H / 2 - n.y) * 0.001;
          n.vx *= 0.9;
          n.vy *= 0.9;
          n.x += n.vx;
          n.y += n.vy;
          n.x = Math.max(30, Math.min(W - 30, n.x));
          n.y = Math.max(30, Math.min(H - 30, n.y));
        });
      };

      const render = () => {
        ctx.clearRect(0, 0, W, H);

        // Edges
        ctx.strokeStyle = '#374151';
        ctx.lineWidth = 1;
        graphData.edges.forEach((edge: GraphEdge) => {
          const source = nodeMap.get(edge.source);
          const target = nodeMap.get(edge.target);
          if (!source || !target) return;
          ctx.beginPath();
          ctx.moveTo(source.x, source.y);
          ctx.lineTo(target.x, target.y);
          ctx.stroke();

          if (edge.label) {
            const mx = (source.x + target.x) / 2;
            const my = (source.y + target.y) / 2;
            ctx.fillStyle = '#6b7280';
            ctx.font = '9px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(edge.label, mx, my - 4);
          }
        });

        // Nodes
        nodes.forEach((n) => {
          const radius = (n.size || 8) + (hoveredNode?.id === n.id ? 3 : 0);
          ctx.beginPath();
          ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
          ctx.fillStyle = n.color;
          ctx.globalAlpha = hoveredNode?.id === n.id ? 1 : 0.85;
          ctx.fill();
          ctx.globalAlpha = 1;

          ctx.fillStyle = '#e5e7eb';
          ctx.font = '11px Inter, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(
            n.label.length > 20 ? n.label.slice(0, 20) + '…' : n.label,
            n.x,
            n.y + radius + 14
          );
        });
      };

      // Run simulation for 150 frames
      let frame = 0;
      const maxFrames = 150;
      const loop = () => {
        simulate();
        render();
        frame++;
        if (frame < maxFrames) requestAnimationFrame(loop);
      };
      loop();

      // Mouse hover detection
      const handleMouse = (e: MouseEvent) => {
        const r = canvas.getBoundingClientRect();
        const mx = e.clientX - r.left;
        const my = e.clientY - r.top;
        let found: CanvasNode | null = null;
        for (const n of nodes) {
          const dx = n.x - mx;
          const dy = n.y - my;
          if (Math.sqrt(dx * dx + dy * dy) < (n.size || 8) + 4) {
            found = n;
            break;
          }
        }
        setHoveredNode(found);
        canvas.style.cursor = found ? 'pointer' : 'default';
      };

      canvas.addEventListener('mousemove', handleMouse);
      return () => canvas.removeEventListener('mousemove', handleMouse);
    },
    [hoveredNode]
  );

  useEffect(() => {
    if (graphResult.data) {
      return draw(graphResult.data);
    }
  }, [graphResult.data, draw]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Knowledge Graph</h1>
          <p className="text-sm text-gray-400">
            Visual exploration of memory relationships
          </p>
        </div>
        <button
          onClick={graphResult.refetch}
          className="flex items-center gap-2 rounded-lg border border-gray-800 px-3 py-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {graphResult.status === 'loading' ? (
        <div className="flex justify-center py-20">
          <Spinner size="lg" />
        </div>
      ) : graphResult.status === 'error' ? (
        <ErrorDisplay error={graphResult.error} onRetry={graphResult.refetch} />
      ) : graphResult.data?.nodes.length === 0 ? (
        <EmptyState message="No graph data available" icon={<Network className="h-10 w-10" />} />
      ) : (
        <Section title={`${graphResult.data?.nodes.length ?? 0} nodes · ${graphResult.data?.edges.length ?? 0} edges`}>
          <div className="relative rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden" style={{ height: '550px' }}>
            <canvas ref={canvasRef} className="h-full w-full" />
            {hoveredNode && (
              <div className="absolute top-4 right-4 rounded-lg border border-gray-700 bg-gray-900/95 p-3 text-xs backdrop-blur-sm">
                <p className="font-semibold text-white">{hoveredNode.label}</p>
                <p className="text-gray-400">Type: {hoveredNode.type}</p>
                <p className="text-gray-500 font-mono">{hoveredNode.id.slice(0, 16)}</p>
              </div>
            )}
            {/* Legend */}
            <div className="absolute bottom-4 left-4 flex gap-4">
              {Object.entries(TYPE_COLORS)
                .filter(([k]) => k !== 'default')
                .map(([type, color]) => (
                  <div key={type} className="flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                    <span className="text-[10px] text-gray-500 capitalize">{type}</span>
                  </div>
                ))}
            </div>
          </div>
        </Section>
      )}
    </div>
  );
}
