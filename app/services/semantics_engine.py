"""
PRD §5c - Argument Representation & Semantics Engine
"""
import networkx as nx
from typing import List, Dict
from app.models.schemas import Argument

def _compute_labeling(arguments: List[Argument]) -> Dict[str, str]:
    """
    Internal function to compute the grounded extension labeling.
    Returns a dictionary mapping argument IDs to their labels: "IN", "OUT", or "UNDEC".
    """
    G = nx.DiGraph()
    
    # Build the graph
    for arg in arguments:
        G.add_node(arg.id, agent=arg.agent)
        
    for arg in arguments:
        for target in arg.attacks:
            if G.has_node(target):
                G.add_edge(arg.id, target)
                
    labels = {arg.id: "UNDEC" for arg in arguments}
    
    while True:
        changed = False
        for node in G.nodes:
            if labels[node] != "UNDEC":
                continue
                
            attackers = list(G.predecessors(node))
            
            if all(labels[atk] == "OUT" for atk in attackers):
                labels[node] = "IN"
                changed = True
            elif any(labels[atk] == "IN" for atk in attackers):
                labels[node] = "OUT"
                changed = True
                
        if not changed:
            break
            
    return labels

def compute_grounded_extension(arguments: List[Argument]) -> Dict[str, List[str]]:
    """
    Computes the grounded extension of an Abstract Argumentation Framework (Dung's AF).
    
    Arguments are represented as nodes, and "attacks" as directed edges.
    The labeling algorithm proceeds as follows (standard fixpoint):
    - Initial state: All nodes are labeled UNDEC (undecided).
    - Label IN: An argument is labeled IN if every attacker of this argument is OUT.
      (This naturally includes arguments with zero attackers).
    - Label OUT: An argument is labeled OUT if at least one attacker of this argument is IN.
    - We iterate through the nodes updating their labels until no more changes occur.
    - Any argument that remains UNDEC after the fixpoint cannot be defended, nor defeated.
    
    Args:
        arguments: List of Argument Pydantic models containing their IDs, attacking targets, and agents.
        
    Returns:
        Dict mapping each side ('advocate', 'skeptic') to a list of its surviving (IN) argument IDs.
    """
    labels = _compute_labeling(arguments)
    
    # Group surviving arguments (labeled IN) by their side
    result = {"advocate": [], "skeptic": []}
    for arg in arguments:
        if labels[arg.id] == "IN":
            result[arg.agent].append(arg.id)
            
    return result
