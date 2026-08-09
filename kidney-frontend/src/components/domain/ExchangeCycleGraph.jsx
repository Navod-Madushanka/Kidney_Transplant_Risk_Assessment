// src/components/domain/ExchangeCycleGraph.jsx
import { useMemo, useState } from "react"

// Reuses this app's existing design tokens rather than a new categorical
// palette (see index.css's comment: the clinical clear/moderate/high-risk
// colors are reserved for clinical status and must never be repurposed for
// decoration). Selected-cycle edges/nodes are never ambiguous by color
// alone here anyway — the solver's packing constraint guarantees selected
// cycles never share a node, so distinct clusters in the circular layout
// already separate them; a numbered badge reinforces that without adding
// hue. See index.css for --color-accent / --color-border / --color-text-muted.
const SELECTED_COLOR = "var(--color-accent)"
const UNSELECTED_COLOR = "var(--color-border)"

const VIEW_SIZE = 560
const CENTER = VIEW_SIZE / 2
const NODE_RADIUS = 20

function layoutRadius(nodeCount) {
  return Math.max(160, Math.min(230, 90 + nodeCount * 6))
}

function nodePosition(index, count, radius) {
  const angle = (2 * Math.PI * index) / count - Math.PI / 2
  return { x: CENTER + radius * Math.cos(angle), y: CENTER + radius * Math.sin(angle) }
}

const PARALLEL_OFFSET = 15

// A quadratic-Bezier "bow" pinches back to the exact same endpoint at each
// node regardless of curve direction, so a mutual pair's two opposite-
// direction arrows still land on top of each other right where the
// arrowhead is — the one place separation actually matters. Shifting both
// endpoints sideways (perpendicular to the node-to-node line) before
// trimming for the node radius instead gives each direction its own
// straight, parallel track and its own distinct arrowhead landing point,
// like a two-lane road rather than a lens of two curves sharing endpoints.
function directedEdgeGeometry(fromCenter, toCenter, sign) {
  const dx = toCenter.x - fromCenter.x
  const dy = toCenter.y - fromCenter.y
  const length = Math.hypot(dx, dy) || 1
  const px = (-dy / length) * PARALLEL_OFFSET * sign
  const py = (dx / length) * PARALLEL_OFFSET * sign

  const shiftedFrom = { x: fromCenter.x + px, y: fromCenter.y + py }
  const shiftedTo = { x: toCenter.x + px, y: toCenter.y + py }

  const sdx = shiftedTo.x - shiftedFrom.x
  const sdy = shiftedTo.y - shiftedFrom.y
  const slength = Math.hypot(sdx, sdy) || 1
  const ux = sdx / slength
  const uy = sdy / slength

  return {
    from: { x: shiftedFrom.x + ux * NODE_RADIUS, y: shiftedFrom.y + uy * NODE_RADIUS },
    to: { x: shiftedTo.x - ux * (NODE_RADIUS + 6), y: shiftedTo.y - uy * (NODE_RADIUS + 6) },
  }
}

/**
 * Usage:
 *   <ExchangeCycleGraph nodes={data.nodes} edges={data.edges} selectedCycles={data.selected_cycles} />
 *
 * Circular layout: every incompatible-pair node placed evenly around a
 * circle, every compatible directed edge (donor -> recipient) drawn as an
 * arrow (a mutual pair's two directions run as parallel offset tracks, see
 * directedEdgeGeometry). Edges inside a selected cycle are highlighted;
 * every other compatible edge is greyed out but still shown, so a
 * coordinator can see what the optimizer passed over.
 */
export default function ExchangeCycleGraph({ nodes, edges, selectedCycles }) {
  const [activePairId, setActivePairId] = useState(null)

  const { positioned, selectedEdgeKeys, selectedPairIds, cycleNumberByPairId } = useMemo(() => {
    const radius = layoutRadius(nodes.length)
    const positioned = nodes.map((node, index) => ({
      ...node,
      ...nodePosition(index, nodes.length, radius),
    }))

    const selectedEdgeKeys = new Set()
    const selectedPairIds = new Set()
    const cycleNumberByPairId = new Map()
    selectedCycles.forEach((cycle, cycleIndex) => {
      const ids = cycle.pair_ids
      ids.forEach((pairId, idx) => {
        selectedPairIds.add(pairId)
        cycleNumberByPairId.set(pairId, cycleIndex + 1)
        const nextId = ids[(idx + 1) % ids.length]
        selectedEdgeKeys.add(`${pairId}->${nextId}`)
      })
    })

    return { positioned, selectedEdgeKeys, selectedPairIds, cycleNumberByPairId }
  }, [nodes, selectedCycles])

  const positionByPairId = useMemo(() => {
    const map = new Map()
    positioned.forEach((node) => map.set(node.pair_id, node))
    return map
  }, [positioned])

  // Render unselected edges first so selected (highlighted) edges layer on
  // top and stay legible where paths cross.
  const orderedEdges = useMemo(() => {
    const isSelected = (edge) => selectedEdgeKeys.has(`${edge.from_pair_id}->${edge.to_pair_id}`)
    return [...edges].sort((a, b) => Number(isSelected(a)) - Number(isSelected(b)))
  }, [edges, selectedEdgeKeys])

  const activeNode = positioned.find((node) => node.pair_id === activePairId) ?? null

  if (nodes.length === 0) {
    return (
      <div className="border border-border rounded-lg p-8 text-center bg-surface">
        <p className="text-[15px] text-text-muted">
          No incompatible pairs in the exchange pool right now.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-4 text-[13px] text-text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-5 rounded-full" style={{ backgroundColor: SELECTED_COLOR }} />
          Selected cycle
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-5 rounded-full opacity-50" style={{ backgroundColor: UNSELECTED_COLOR }} />
          Compatible, not selected
        </span>
        <span>Arrows point donor → recipient.</span>
      </div>

      <div className="overflow-x-auto border border-border rounded-lg bg-surface">
        <svg
          viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`}
          className="w-full min-w-[420px] max-w-[560px] mx-auto"
          role="img"
          aria-label="Paired exchange candidate graph"
        >
          <defs>
            <marker id="arrow-selected" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill={SELECTED_COLOR} />
            </marker>
            <marker id="arrow-unselected" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill={UNSELECTED_COLOR} />
            </marker>
          </defs>

          {orderedEdges.map((edge, index) => {
            const from = positionByPairId.get(edge.from_pair_id)
            const to = positionByPairId.get(edge.to_pair_id)
            if (!from || !to) return null

            const selected = selectedEdgeKeys.has(`${edge.from_pair_id}->${edge.to_pair_id}`)
            const hasReverse = edges.some(
              (other) => other.from_pair_id === edge.to_pair_id && other.to_pair_id === edge.from_pair_id
            )
            // No extra id-based sign needed: the perpendicular itself
            // already flips when from/to swap (it's derived from this
            // edge's own direction vector), so a fixed +1 here already
            // pushes a reciprocal pair's two edges to opposite sides — an
            // id-based flip on top of that would cancel it back out.
            const sign = hasReverse ? 1 : 0
            const line = directedEdgeGeometry(from, to, sign)

            return (
              <line
                key={`${edge.from_pair_id}-${edge.to_pair_id}-${index}`}
                x1={line.from.x}
                y1={line.from.y}
                x2={line.to.x}
                y2={line.to.y}
                stroke={selected ? SELECTED_COLOR : UNSELECTED_COLOR}
                strokeWidth={selected ? 2.5 : 1.5}
                opacity={selected ? 1 : 0.45}
                markerEnd={selected ? "url(#arrow-selected)" : "url(#arrow-unselected)"}
              />
            )
          })}

          {positioned.map((node) => {
            const selected = selectedPairIds.has(node.pair_id)
            const active = node.pair_id === activePairId
            const cycleNumber = cycleNumberByPairId.get(node.pair_id)
            return (
              <g
                key={node.pair_id}
                transform={`translate(${node.x}, ${node.y})`}
                className="cursor-pointer"
                onMouseEnter={() => setActivePairId(node.pair_id)}
                onMouseLeave={() => setActivePairId((current) => (current === node.pair_id ? null : current))}
                onClick={() => setActivePairId((current) => (current === node.pair_id ? null : node.pair_id))}
              >
                <circle
                  r={NODE_RADIUS}
                  fill="var(--color-surface)"
                  stroke={selected ? SELECTED_COLOR : "var(--color-text-muted)"}
                  strokeWidth={active ? 3 : selected ? 2.5 : 1.5}
                />
                <text textAnchor="middle" dy="-1" className="text-[11px] font-semibold fill-text select-none">
                  {node.patient_blood_type}
                </text>
                <text textAnchor="middle" dy="10" className="text-[9px] fill-text-muted select-none">
                  ←{node.donor_blood_type}
                </text>
                {cycleNumber && (
                  <text
                    x={NODE_RADIUS - 2}
                    y={-NODE_RADIUS + 2}
                    textAnchor="middle"
                    className="text-[9px] font-bold select-none"
                    fill={SELECTED_COLOR}
                  >
                    {cycleNumber}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      <div className="min-h-[64px] border border-border rounded-lg bg-surface p-3 text-[13px]">
        {activeNode ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <p className="col-span-2 font-semibold text-text">
              Recipient blood type {activeNode.patient_blood_type} · Donor blood type {activeNode.donor_blood_type}
              {cycleNumberByPairId.has(activeNode.pair_id) && (
                <span className="ml-2 text-accent">· in cycle {cycleNumberByPairId.get(activeNode.pair_id)}</span>
              )}
            </p>
            <p className="text-text-muted">Recipient: {activeNode.patient_hospital_name} · {activeNode.patient_doctor_full_name}</p>
            <p className="text-text-muted">Donor: {activeNode.donor_hospital_name} · {activeNode.donor_doctor_full_name}</p>
          </div>
        ) : (
          <p className="text-text-muted">Hover or tap a pair to see its hospital and doctor.</p>
        )}
      </div>
    </div>
  )
}
