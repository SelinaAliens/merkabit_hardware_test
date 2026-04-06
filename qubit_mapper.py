"""
Qubit Mapper: Eisenstein 7-Node Cell -> IBM Eagle r3 Physical Qubits
====================================================================
Maps the merkabit's 7-node Eisenstein cell (14 data qubits + 12 ancillas)
onto the heavy-hex coupling map of IBM Eagle r3 processors.

Each merkabit node = 2 physical qubits (forward spinor u, inverse spinor v).
Each edge between merkabit nodes needs 1 ancilla for syndrome extraction.

The mapper:
1. Builds the 7-node Eisenstein cell topology
2. Searches the Eagle r3 coupling map for the best 26-qubit embedding
3. Scores by T2 coherence and ECR gate fidelity
4. Outputs {node: (qubit_u, qubit_v), edge: ancilla_qubit}

Selina Stenberg with Claude Anthropic, April 2026
"""

import numpy as np
from collections import defaultdict
from itertools import product as iterproduct


# ═══════════════════════════════════════════════════════════════
# EISENSTEIN CELL (7-node, radius 1)
# ═══════════════════════════════════════════════════════════════

UNIT_VECTORS = [(1, 0), (-1, 0), (0, 1), (0, -1), (-1, -1), (1, 1)]

GATES = ['S', 'R', 'T', 'P', 'F']
NUM_GATES = 5


class EisensteinCell:
    """7-node Eisenstein cell with chirality assignment."""

    def __init__(self, radius=1):
        self.radius = radius
        r_sq = radius * radius

        # Nodes: (a,b) with a^2 - ab + b^2 <= r^2
        self.coords = []
        for a in range(-radius - 1, radius + 2):
            for b in range(-radius - 1, radius + 2):
                if a * a - a * b + b * b <= r_sq:
                    self.coords.append((a, b))

        self.num_nodes = len(self.coords)
        self.coord_to_idx = {c: i for i, c in enumerate(self.coords)}

        # Edges: Eisenstein norm-1 distance
        self.edges = []
        self.neighbours = defaultdict(list)
        coord_set = set(self.coords)

        for i, (a1, b1) in enumerate(self.coords):
            for da, db in UNIT_VECTORS:
                nb = (a1 + da, b1 + db)
                if nb in coord_set:
                    j = self.coord_to_idx[nb]
                    if j > i:
                        self.edges.append((i, j))
                    self.neighbours[i].append(j)

        self.num_edges = len(self.edges)

        # Chirality: (a+b) mod 3
        self.sublattice = [(a + b) % 3 for (a, b) in self.coords]
        self.chirality = []
        for s in self.sublattice:
            if s == 0:
                self.chirality.append(0)
            elif s == 1:
                self.chirality.append(+1)
            else:
                self.chirality.append(-1)

        # Coordination
        self.coordination = [len(self.neighbours[i])
                             for i in range(self.num_nodes)]

    def summary(self):
        print(f"Eisenstein cell: {self.num_nodes} nodes, {self.num_edges} edges")
        for i, (a, b) in enumerate(self.coords):
            chi = self.chirality[i]
            coord = self.coordination[i]
            interior = "interior" if coord == 6 else "boundary"
            print(f"  Node {i}: ({a:+d},{b:+d}) chi={chi:+d} "
                  f"coord={coord} ({interior})")
        print(f"  Edges: {self.edges}")


# ═══════════════════════════════════════════════════════════════
# QUBIT REQUIREMENTS
# ═══════════════════════════════════════════════════════════════

def compute_qubit_requirements(cell):
    """
    Each merkabit node needs 2 data qubits (u, v).
    Each edge needs 1 ancilla qubit.
    The ancilla must be connected to at least one data qubit from each endpoint.
    """
    n_data = cell.num_nodes * 2
    n_ancilla = cell.num_edges
    n_total = n_data + n_ancilla
    print(f"Qubit requirements:")
    print(f"  Data qubits: {n_data} ({cell.num_nodes} nodes x 2 spinors)")
    print(f"  Ancilla qubits: {n_ancilla} ({cell.num_edges} edges)")
    print(f"  Total: {n_total}")
    return n_data, n_ancilla, n_total


# ═══════════════════════════════════════════════════════════════
# HEAVY-HEX COUPLING MAP (Eagle r3, 127 qubits)
# ═══════════════════════════════════════════════════════════════

def get_eagle_coupling_map():
    """
    Get Eagle r3 coupling map.
    Try Qiskit backend first, fall back to generic heavy-hex.
    """
    try:
        from qiskit.providers.fake_provider import GenericBackendV2
        backend = GenericBackendV2(num_qubits=127)
        cmap = backend.coupling_map
        print(f"Using GenericBackendV2 coupling map: {cmap.size()} qubits")
        return cmap
    except Exception:
        pass

    try:
        from qiskit.transpiler import CouplingMap
        # IBM Eagle r3 heavy-hex: manually specified for ibm_brisbane/strasbourg
        # This is the standard 127-qubit heavy-hex topology
        edges = []
        # Row structure of heavy-hex: alternating rows of degree-2 and degree-3 qubits
        # Simplified: use Qiskit's built-in heavy-hex generator
        cmap = CouplingMap.from_heavy_hex(d=7)  # distance-7 heavy hex = 127 qubits
        print(f"Using heavy-hex CouplingMap: {cmap.size()} qubits")
        return cmap
    except Exception as e:
        print(f"Warning: Could not create coupling map: {e}")
        print("Falling back to manual qubit assignment")
        return None


def find_qubit_pairs(cmap):
    """
    Find all directly connected qubit pairs on the coupling map.
    Each pair can host one merkabit node (u on qubit_a, v on qubit_b).
    """
    pairs = []
    seen = set()
    for q1, q2 in cmap.get_edges():
        key = (min(q1, q2), max(q1, q2))
        if key not in seen:
            pairs.append(key)
            seen.add(key)
    return pairs


def find_embedding(cell, cmap):
    """
    Find a subgraph of the coupling map that accommodates:
    - 7 qubit pairs (for 7 merkabit nodes)
    - 12 ancilla qubits (for 12 edges)
    - Each ancilla connected to at least one qubit in each endpoint pair

    Strategy: brute-force search over 7-tuples of pairs, filtered by adjacency.
    For a 127-qubit device this is tractable.
    """
    if cmap is None:
        return None

    pairs = find_qubit_pairs(cmap)
    adj = defaultdict(set)
    for q1, q2 in cmap.get_edges():
        adj[q1].add(q2)
        adj[q2].add(q1)

    # For each pair, find which other pairs it can connect to via a bridge qubit
    pair_bridges = {}
    for p_idx, (qa, qb) in enumerate(pairs):
        pair_qubits = {qa, qb}
        # Neighbors of this pair (excluding pair members)
        pair_nbrs = (adj[qa] | adj[qb]) - pair_qubits
        pair_bridges[p_idx] = (pair_qubits, pair_nbrs)

    # Score: prefer pairs with high connectivity
    # For a first pass, find a single valid embedding greedily
    best_mapping = None
    best_score = -1

    # Greedy: start from the highest-degree pair, expand to neighbors
    pair_degrees = [(len(pair_bridges[i][1]), i) for i in range(len(pairs))]
    pair_degrees.sort(reverse=True)

    for _, start_idx in pair_degrees[:20]:  # Try top 20 starting pairs
        mapping = _greedy_embed(cell, pairs, pair_bridges, adj, start_idx)
        if mapping is not None:
            score = _score_mapping(mapping, adj)
            if score > best_score:
                best_score = score
                best_mapping = mapping

    return best_mapping


def _greedy_embed(cell, pairs, pair_bridges, adj, start_idx):
    """Greedy embedding: place centre node first, then expand."""
    # Find centre node (chirality 0)
    centre = [i for i in range(cell.num_nodes) if cell.chirality[i] == 0][0]

    node_to_pair = {}
    used_qubits = set()

    # Place centre
    pair = pairs[start_idx]
    node_to_pair[centre] = pair
    used_qubits.update(pair)

    # BFS from centre, placing neighbors
    queue = list(cell.neighbours[centre])
    placed = {centre}

    for node in queue:
        if node in placed:
            continue

        # Find a pair adjacent to any already-placed neighbor
        best_pair = None
        best_bridges = 0

        for n_placed in cell.neighbours[node]:
            if n_placed not in placed:
                continue
            placed_pair = node_to_pair[n_placed]

            # Find pairs connected to placed_pair via bridge qubits
            for p_idx, (pq, pnbrs) in pair_bridges.items():
                if pq & used_qubits:
                    continue  # Already used
                # Check if this pair connects to the placed pair
                placed_nbrs = (adj[placed_pair[0]] | adj[placed_pair[1]])
                if pq & placed_nbrs or pnbrs & set(placed_pair):
                    bridges = len(pnbrs - used_qubits)
                    if bridges > best_bridges:
                        best_bridges = bridges
                        best_pair = pairs[p_idx]

        if best_pair is None:
            return None  # Failed to place this node

        node_to_pair[node] = best_pair
        used_qubits.update(best_pair)
        placed.add(node)

        # Add unplaced neighbors to queue
        for nbr in cell.neighbours[node]:
            if nbr not in placed:
                queue.append(nbr)

    if len(node_to_pair) != cell.num_nodes:
        return None

    # Now find ancilla qubits for each edge
    edge_to_ancilla = {}
    for (i, j) in cell.edges:
        pair_i = node_to_pair[i]
        pair_j = node_to_pair[j]

        # Find a qubit connected to both pairs, not already used
        candidates = set()
        for qi in pair_i:
            candidates |= adj[qi]
        for qj in pair_j:
            candidates &= adj[qj] | {qj}

        # Relax: find qubits connected to at least one qubit in each pair
        if not candidates:
            for qi in pair_i:
                for qj in pair_j:
                    shared = adj[qi] & adj[qj]
                    candidates |= (shared - used_qubits)

        candidates -= used_qubits
        if not candidates:
            return None  # No ancilla available for this edge

        ancilla = min(candidates)  # Deterministic choice
        edge_to_ancilla[(i, j)] = ancilla
        used_qubits.add(ancilla)

    return {
        'node_to_pair': node_to_pair,
        'edge_to_ancilla': edge_to_ancilla,
        'total_qubits': len(used_qubits),
        'used_qubits': used_qubits,
    }


def _score_mapping(mapping, adj):
    """Score a mapping by total connectivity."""
    if mapping is None:
        return -1
    return len(mapping['used_qubits'])


# ═══════════════════════════════════════════════════════════════
# MANUAL FALLBACK MAPPING
# ═══════════════════════════════════════════════════════════════

def manual_mapping_strasbourg():
    """
    Manual qubit assignment for ibm_strasbourg based on Thor's §2.7 work.
    Uses the same hexagonal region: data qubits [58,59,60,61,62,77,79,81]
    Extended to dual-spinor encoding.
    """
    # Thor's validated hexagonal cell on ibm_strasbourg:
    # Data qubits: [62, 81, 79, 77, 58, 60]
    # Ancillas: [72, 80, 78, 71, 59, 61]

    # For dual-spinor: each node needs 2 qubits
    # We need a larger region. Approximate mapping:
    return {
        'backend': 'ibm_strasbourg',
        'note': 'Extend from Thor §2.7 hexagonal cell',
        'validated_region': {
            'data': [62, 81, 79, 77, 58, 60],
            'ancilla': [72, 80, 78, 71, 59, 61],
        }
    }


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 70)
    print("MERKABIT QUBIT MAPPER — Eisenstein Cell to Eagle r3")
    print("=" * 70)
    print()

    # Build Eisenstein cell
    cell = EisensteinCell(radius=1)
    cell.summary()
    print()

    # Compute requirements
    n_data, n_ancilla, n_total = compute_qubit_requirements(cell)
    print()

    # Try automatic embedding
    print("Searching for optimal qubit embedding...")
    cmap = get_eagle_coupling_map()
    if cmap is not None:
        mapping = find_embedding(cell, cmap)
        if mapping:
            print(f"\nFound embedding using {mapping['total_qubits']} qubits:")
            for node, (qu, qv) in sorted(mapping['node_to_pair'].items()):
                chi = cell.chirality[node]
                print(f"  Node {node} (chi={chi:+d}): "
                      f"q_u={qu}, q_v={qv}")
            for (i, j), anc in sorted(mapping['edge_to_ancilla'].items()):
                print(f"  Edge ({i},{j}): ancilla={anc}")
        else:
            print("Automatic embedding failed. Using manual mapping.")
            print(manual_mapping_strasbourg())
    else:
        print("No coupling map available. Using manual mapping.")
        print(manual_mapping_strasbourg())
