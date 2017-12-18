import sys
import pprint
import importlib
import copy

class Spec:

  def __init__(self, nodes, edges):
    self.nodes = {}
    self.edges = {}
    for node in nodes:
      self.nodes[node] = nodes[node]
    for edge in edges:
      self.edges[edge] = edges[edge]

  def remove_node(self, node_name):
      if node_name in self.nodes:
        del self.nodes[node_name]
 
  def remove_edge(self, edge_name):
      if edge_name in self.edges:
        del self.edges[edge_name]


# Get name of cond_node
def get_name_of_cond_node(input_spec, cond_block_name):
  for node in input_spec.nodes:
    if input_spec.nodes[node]['type'] == 'condition':
      if input_spec.nodes[node]['condition'] == cond_block_name:
        return node
  return "error" 

# Get parents of a given node
def get_parent_of_node(input_spec, node_name):

  parent = {}

  for edge in input_spec.edges :
    if edge[1] == node_name :
      parent[edge[1]]['delay'] = input_spec[edge]['delay']
      parent[edge[1]]['dep_type'] = input_spec[edge]['dep_type']

  return parent

# Get child branches of a given node
def get_branch_of_node(input_spec, node_name, branch_value):

  branch = {}

  for edge in input_spec.edges :
    if (edge[0] == node_name) :
      if (input_spec.edges[edge]['condition'] == branch_value):
        branch[edge[0]] = {}
        branch[edge[0]]['delay'] = input_spec.edges[edge]['delay']
        branch[edge[0]]['dep_type'] = input_spec.edges[edge]['dep_type']

  return branch

# Remove node for new branches
def remove_node_from_branch(branch_spec, node_name, input_spec):
  
  print (node_name)
  if node_name in branch_spec.nodes:
    branch_spec.remove_node(node_name)

  # remove edges
  
  for edge in input_spec.edges:
    if ( edge[0] == node_name ) | ( edge[1] == node_name ) :
      print ( edge )
      branch_spec.remove_edge((edge[0], edge[1]))



# add edges from parents to children in new  spec
def add_edges_from_parents(branch_spec, parents, children):
  for node1 in parents:
    for node2 in children:
      branch_spec.edges[(node1, node2)] = parents[node1]
      

if __name__ == "__main__":
  # Cmd line args
  if (len(sys.argv) != 5):
    print ("Usage: ", sys.argv[0], " <DAG file> <HW file> <latency file> <conditional_block_name>")
    exit(1)
  elif (len(sys.argv) == 5):
    input_file   = sys.argv[1]
    hw_file      = sys.argv[2]
    latency_file = sys.argv[3]
    cond_block_name = sys.argv[4]


  # Input specification
  input_spec_pk = importlib.import_module(input_file, "*")
  hw_spec    = importlib.import_module(hw_file, "*")
  latency_spec=importlib.import_module(latency_file, "*")
  input_spec_pk.action_fields_limit = hw_spec.action_fields_limit
  input_spec_pk.match_unit_limit    = hw_spec.match_unit_limit
  input_spec_pk.match_unit_size     = hw_spec.match_unit_size
  input_spec_pk.action_proc_limit   = hw_spec.action_proc_limit
  input_spec_pk.match_proc_limit    = hw_spec.match_proc_limit

  # make copies of two specs
  input_spec = Spec(input_spec_pk.nodes, input_spec_pk.edges)
  true_branch_spec = Spec(input_spec_pk.nodes, input_spec_pk.edges)
  false_branch_spec = Spec(input_spec_pk.nodes, input_spec_pk.edges)

  #pprint.pprint(input_spec.)

  # get parents, true-branch, false_branch of conditional node
  cond_node = get_name_of_cond_node(input_spec, cond_block_name)
  if (cond_node == 'error'):
    print ('Conditional block not found')
    exit(1)

  parents = get_parent_of_node(input_spec, cond_node)
  true_branch = get_branch_of_node(input_spec, cond_node, True)
  false_branch = get_branch_of_node(input_spec, cond_node, False)

  # remove_conditional_node_from_branches
  remove_node_from_branch(true_branch_spec, cond_node, input_spec)
  remove_node_from_branch(false_branch_spec, cond_node, input_spec)

  # add edges from parents to child branches
  add_edges_from_parents(true_branch_spec, parents, true_branch)
  add_edges_from_parents(false_branch_spec, parents, false_branch)

  pprint.pprint(true_branch_spec.edges)
  #pprint.pprint(false_branch_spec)
    
