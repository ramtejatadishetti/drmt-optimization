import networkx as nx
import sys
import importlib

INPUT_SPEC_FILE = 'orig'
HW = 'large_hw'
LATENCY = 'drmt_latencies'
COND_NAME = '(valid ipv4)'

# Get name of cond_node
def get_name_of_cond_node(input_spec, cond_block_name):
  for node in input_spec.nodes:
    if input_spec.nodes[node]['type'] == 'condition':
      if input_spec.nodes[node]['condition'] == cond_block_name:
        return node
  return "error" 

# Get child branches of a given conditional node, and the branching value 
def get_branch_of_node(input_spec, node_name, branch_value):

  branch = {}

  for edge in input_spec.edges :
    if (edge[0] == node_name) :
      if (input_spec.edges[edge]['condition'] == branch_value):
        branch[edge[0]] = {}
        branch[edge[0]]['delay'] = input_spec.edges[edge]['delay']
        branch[edge[0]]['dep_type'] = input_spec.edges[edge]['dep_type']

  return branch

if __name__ == "__main__":
  # Cmd line args
  '''
  if (len(sys.argv) != 5):
    print ("Usage: ", sys.argv[0], " <DAG file> <HW file> <latency file> <conditional_block>")
    exit(1)
  elif (len(sys.argv) == 5):
    input_file   = sys.argv[1]
    hw_file      = sys.argv[2]
    latency_file = sys.argv[3]
    cond_block_name = sys.argv[4]
  '''
  
  # Input specification
  input_spec = importlib.import_module(INPUT_SPEC_FILE, "*")
  hw_spec    = importlib.import_module(HW, "*")
  latency_spec=importlib.import_module(LATENCY, "*")
  cond_block_name = COND_NAME

  input_spec.action_fields_limit = hw_spec.action_fields_limit
  input_spec.match_unit_limit    = hw_spec.match_unit_limit
  input_spec.match_unit_size     = hw_spec.match_unit_size
  input_spec.action_proc_limit   = hw_spec.action_proc_limit
  input_spec.match_proc_limit    = hw_spec.match_proc_limit

  # Create G1, G2
  G1 = nx.DiGraph()
  G1.add_nodes_from(input_spec.nodes)
  G1.add_edges_from(input_spec.edges)
  

  G2 = nx.DiGraph()
  G2.add_nodes_from(input_spec.nodes)
  G2.add_edges_from(input_spec.edges)
  
  root_node_list = []
  for node,in_degree in G1.in_degree().items():
    if(in_degree == 0):
      root_node_list.append(node)

  print ("Root_node_list", root_node_list)
  #get name of conditional node 
  cond_node = get_name_of_cond_node(input_spec, cond_block_name)
  print("condition_node", cond_node)

  node_visit_markers = {}





