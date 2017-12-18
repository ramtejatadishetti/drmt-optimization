import collections
import importlib
import math
import sys
from itertools import *

import networkx as nx
from gurobipy import *

from printers import *
from schedule_dag import ScheduleDAG
import pprint as pp
from finalsolution import Finalsolution

BRANCH1_SPEC_FILE = 'ipv4_cdffdcombined'
BRANCH2_SPEC_FILE = 'ipv6_fdkjfdcombined'
HW = 'large_hwfd'
LATENCY = 'drmt_fdlatencies'


def get_common_nodes(graph1, graph2):
    mapping = {}
    branch1_nodes = graph1.nodes()
    branch2_nodes = graph2.nodes()

    for i in range(0, len(branch1_nodes)) :
        for j in range(0, len(branch2_nodes)) :
            if branch1_nodes[i] == branch2_nodes[j] :
                mapping[i] = j

    return mapping

def model_ilp(graph1, graph2, mapping, branch1_spec, branch2_spec, period, minute_limit):

    branch1_nodes = graph1.nodes()
    branch2_nodes = graph2.nodes()

    branch1_edges = graph1.edges()
    branch2_edges = graph2.edges()

    cpath1, cplat1 = graph1.critical_path()
    cpath2, cplat2 = graph2.critical_path()

    if cplat1 > cplat2 :
        cplat = cplat1
    else:
        cplat = cplat2

    Q_MAX = int(math.ceil(1.5 * cplat / period))
    T = period

    print("Q_MAX", Q_MAX)
    print("PERIOD", T)    

    match_nodes1 = graph1.nodes(select='match')
    match_nodes2 = graph2.nodes(select='match')

    action_nodes1 = graph1.nodes(select='action')
    action_nodes2 = graph2.nodes(select='action')

    m = Model()
    m.setParam("LogToConsole", 0)

    t1 = m.addVars(branch1_nodes, lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="t1")
    qr1 = m.addVars(list(itertools.product(branch1_nodes, range(Q_MAX), range(T))), \
                    vtype=GRB.BINARY, name="qr1")
    any_match1 = m.addVars(list(itertools.product(range(Q_MAX), range(T))), \
                    vtype=GRB.BINARY, name="any_match1")
    any_action1 = m.addVars(list(itertools.product(range(Q_MAX), range(T))), \
                    vtype=GRB.BINARY, name="any_action1")

    t2 = m.addVars(branch2_nodes, lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="t2")
    qr2 = m.addVars(list(itertools.product(branch2_nodes, range(Q_MAX), range(T))), \
                    vtype=GRB.BINARY, name="qr2")

    any_match2 = m.addVars(list(itertools.product(range(Q_MAX), range(T))), \
                    vtype=GRB.BINARY, name="any_match2")
    any_action2 = m.addVars(list(itertools.product(range(Q_MAX), range(T))), \
                    vtype=GRB.BINARY, name="any_action2")


    length = m.addVar(lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="length")
    m.setObjective(length, GRB.MINIMIZE)

    m.addConstrs((t1[v] <= length for v in branch1_nodes), "constr_length_is_max1")
    m.addConstrs((t2[v] <= length for v in branch2_nodes), "constr_length_is_max2")

    m.addConstrs((sum(qr1[v, q, r] for q in range(Q_MAX) for r in range(T)) == 1 for v in branch1_nodes),\
                     "constr_unique_quotient_remainder1")

    m.addConstrs((sum(qr2[v, q, r] for q in range(Q_MAX) for r in range(T)) == 1 for v in branch2_nodes),\
                     "constr_unique_quotient_remainder2")
    
    # t(v) = Sum ( (q*T+r)indicator(q,r,v) ) for all q, for all v
    m.addConstrs((t1[v] == \
                      sum(q * qr1[v, q, r] for q in range(Q_MAX) for r in range(T)) * T + \
                      sum(r * qr1[v, q, r] for q in range(Q_MAX) for r in range(T)) \
                      for v in branch1_nodes), "constr_division1")
    
    m.addConstrs((t2[v] == \
                      sum(q * qr2[v, q, r] for q in range(Q_MAX) for r in range(T)) * T + \
                      sum(r * qr2[v, q, r] for q in range(Q_MAX) for r in range(T)) \
                      for v in branch2_nodes), "constr_division2")
    

    # Respect dependencies in DAG1
    m.addConstrs((t1[v] - t1[u] >= graph1.edge[u][v]['delay'] for (u,v) in branch1_edges),\
                     "constr_dag_dependencies1")
    
    # Respect dependencies in DAG2
    m.addConstrs((t2[v] - t2[u] >= graph2.edge[u][v]['delay'] for (u,v) in branch2_edges),\
                     "constr_dag_dependencies2")
    
    # Hardware constraints
    # Number of match units does not exceed match_unit_limit
    # for every time step (j) < T, check the total match unit requirements
    # across all nodes (v) that can be "rotated" into this time slot.
    m.addConstrs((sum(math.ceil((1.0 * graph1.node[v]['key_width']) / branch1_spec.match_unit_size) * qr1[v, q, r]\
                      for v in match_nodes1 for q in range(Q_MAX))\
                      <= branch1_spec.match_unit_limit for r in range(T)),\
                      "constr_match_units1")
    
    m.addConstrs((sum(math.ceil((1.0 * graph2.node[v]['key_width']) / branch2_spec.match_unit_size) * qr2[v, q, r]\
                      for v in match_nodes2 for q in range(Q_MAX))\
                      <= branch2_spec.match_unit_limit for r in range(T)),\
                      "constr_match_units2")
    
    # The action field resource constraint (similar comments to above)
    m.addConstrs((sum(graph1.node[v]['num_fields'] * qr1[v, q, r]\
                      for v in action_nodes1 for q in range(Q_MAX))\
                      <= branch1_spec.action_fields_limit for r in range(T)),\
                      "constr_action_fields1")
    
    m.addConstrs((sum(graph2.node[v]['num_fields'] * qr2[v, q, r]\
                      for v in action_nodes2 for q in range(Q_MAX))\
                      <= branch2_spec.action_fields_limit for r in range(T)),\
                      "constr_action_fields2")

    # First, detect if there is any (at least one) match/action operation from packet q in time slot r
    # if qr[v, q, r] = 1 for any match node, then any_match[q,r] must = 1 (same for actions)
    # Notice that any_match[q, r] may be 1 even if all qr[v, q, r] are zero
    m.addConstrs((sum(qr1[v, q, r] for v in match_nodes1) <= (len(match_nodes1) * any_match1[q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_match1")
    
    m.addConstrs((sum(qr2[v, q, r] for v in match_nodes2) <= (len(match_nodes2) * any_match2[q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_match2")

    m.addConstrs((sum(qr1[v, q, r] for v in action_nodes1) <= (len(action_nodes1) * any_action1[q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_action1")

    m.addConstrs((sum(qr2[v, q, r] for v in action_nodes2) <= (len(action_nodes2) * any_action2[q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_action2")

    # Second, check that, for any r, the summation over q of any_match[q, r] is under proc_limits
    m.addConstrs((sum(any_match1[q, r] for q in range(Q_MAX)) <= branch1_spec.match_proc_limit\
                      for r in range(T)), "constr_match_proc1")
    m.addConstrs((sum(any_match2[q, r] for q in range(Q_MAX)) <= branch2_spec.match_proc_limit\
                      for r in range(T)), "constr_match_proc2")
  

    m.addConstrs((sum(any_action1[q, r] for q in range(Q_MAX)) <= branch1_spec.action_proc_limit\
                      for r in range(T)), "constr_action_proc")
    m.addConstrs((sum(any_action2[q, r] for q in range(Q_MAX)) <= branch2_spec.action_proc_limit\
                      for r in range(T)), "constr_action_proc")
   
    # add constraints for common things
    m.addConstrs((t1[ branch1_nodes[v] ] == t2[ branch2_nodes[common_nodes_mapping[v]]] for v in common_nodes_mapping), "common-constarint")

    m.setParam('TimeLimit', minute_limit * 60)
    m.optimize()
    ret = m.Status
    if (ret == GRB.INFEASIBLE):
        print ('Infeasible')
        return None
    elif ((ret == GRB.TIME_LIMIT) or (ret == GRB.INTERRUPTED)):
        if (m.SolCount == 0):
            print ('Hit time limit or interrupted, no solution found yet')
            return None
        else:
            print ('Hit time limit or interrupted, suboptimal solution found with gap ', m.MIPGap)
    elif (ret == GRB.OPTIMAL):
        print ('Optimal solution found with gap ', m.MIPGap)
    else:
        print ('Return code is ', ret)
        assert(False)
    
    
    time_of_op = {}
    ops_at_time = collections.defaultdict(list)
    ops_on_ring = collections.defaultdict(list)
    fin_length = length + 1 

    final_solution = Finalsolution()
  
    for node in branch1_nodes:
        tv = int(t1[node].x)
        time_of_op[node] = tv
        ops_at_time[tv].append(node)
    
    for node in branch2_nodes:
        if node not in time_of_op:
            tv = int(t2[node].x)
            time_of_op[node] = tv
            ops_at_time[tv].append(node)

    for pd in range(T):
        final_solution.match_key_usage1[pd] = 0
        final_solution.action_fields_usage1[pd] = 0
        final_solution.match_units_usage1[pd] = 0
        final_solution.match_proc_set1[pd] = set()
        final_solution.match_proc_usage1[pd] = 0
        final_solution.action_proc_usage1[pd] = 0
        final_solution.action_proc_set1[pd] = set()

        final_solution.match_key_usage2[pd] = 0
        final_solution.action_fields_usage2[pd] = 0
        final_solution.match_units_usage2[pd] = 0
        final_solution.match_proc_set2[pd] = set()
        final_solution.match_proc_usage2[pd] = 0
        final_solution.action_proc_usage2[pd] = 0
        final_solution.action_proc_set2[pd] = set()



    # compute stats for branch1
    for node in graph1.nodes():
        k = time_of_op[node] / period
        r = time_of_op[node] % period
        ops_on_ring[r].append('p[%d].%s' % (k,node))

    
        if graph1.node[node]['type'] == 'match':
            final_solution.match_key_usage1[r] += graph1.node[node]['key_width']
            final_solution.match_units_usage1[r] += math.ceil((1.0 * graph1.node[node]['key_width'])/ branch1_spec.match_unit_size)
            final_solution.match_proc_set1[r].add(k)
            final_solution.match_proc_usage1[r] = len(final_solution.match_proc_set1[r])

        else:
            final_solution.action_fields_usage1[r] += graph1.node[node]['num_fields']
            final_solution.action_proc_set1[r].add(k)
            final_solution.action_proc_usage1[r] = len(final_solution.action_proc_set1[r])
    

    # compute stats for branch2
    for node in graph2.nodes():
        k = time_of_op[node] / period
        r = time_of_op[node] % period
        ops_on_ring[r].append('p[%d].%s' % (k,node))

    
        if graph2.node[node]['type'] == 'match':
            final_solution.match_key_usage2[r] += graph2.node[node]['key_width']
            final_solution.match_units_usage2[r] += math.ceil((1.0 * graph2.node[node]['key_width'])/ branch2_spec.match_unit_size)
            final_solution.match_proc_set2[r].add(k)
            final_solution.match_proc_usage2[r] = len(final_solution.match_proc_set2[r])

        else:
            final_solution.action_fields_usage2[r] += graph2.node[node]['num_fields']
            final_solution.action_proc_set2[r].add(k)
            final_solution.action_proc_usage2[r] = len(final_solution.action_proc_set2[r])
    
    
    final_solution.ops_at_time = ops_at_time
    final_solution.ops_on_ring = ops_on_ring
    final_solution.length = length
    final_solution.time_of_op = time_of_op

    return final_solution

if __name__ == "__main__":
    # Read specification for each branch
    if (len(sys.argv) != 9):
        print ("Usage: ", sys.argv[0], " <DAG file1> <DAG file2> <DAG file3> <DAG file 4>  <HW file> <latency file> <time limit in mins> <binary_up_limit>")
        exit(1)
    elif (len(sys.argv) == 9):
        BRANCH1_SPEC_FILE  = sys.argv[1]
        BRANCH2_SPEC_FILE  = sys.argv[2]

        BRANCH3_SPEC_FILE  = sys.argv[3]
        BRANCH4_SPEC_FILE  = sys.argv[4]
        
        HW = sys.argv[5]
        LATENCY = sys.argv[6]
        minute_limit = int(sys.argv[7])
        binary_up_limit = int(sys.argv[8])

    branch_spec = {}
    branch_spec[0] = importlib.import_module(BRANCH1_SPEC_FILE, "*")
    branch_spec[1] = importlib.import_module(BRANCH2_SPEC_FILE, "*")

    branch_spec[2] = importlib.import_module(BRANCH3_SPEC_FILE, "*")
    branch_spec[3] = importlib.import_module(BRANCH4_SPEC_FILE, "*")

    hw_spec = importlib.import_module(HW, "*")
    latency_spec = importlib.import_module(LATENCY, "*")

    for i in range(0, 4):
        branch_spec[i].action_fields_limit = hw_spec.action_fields_limit
        branch_spec[i].match_unit_limit = hw_spec.match_unit_limit
        branch_spec[i].match_unit_size = hw_spec.match_unit_size
        branch_spec[i].action_proc_limit = hw_spec.action_proc_limit
        branch_spec[i].match_proc_limit = hw_spec.match_proc_limit    


    # Create graphs for all branches
    graphs_map = {}

    for i in range(0,4):
        graphs_map[i] = ScheduleDAG()
        graphs_map[i].create_dag(branch_spec[i].nodes, branch_spec[i].edges, latency_spec)
    
    common_nodes_mapping ={}
    for i in range(0,3):
        common_nodes_mapping[i] = {}
        for j in range(i+1,4):
            common_nodes_mapping[i][j] = get_common_nodes(graphs_map[i], graphs_map[j])
    
    match_key_size = {}
    for i in range(0, 4):
        print("Branch " + str(i) + " nodes length" , len(graphs_map[i].nodes()))
        print("Branch " + str(i) + " match nodes length" , len(graphs_map[i].nodes(select='match')))
        print("Branch " + str(i) + " action nodes length" , len(graphs_map[i].nodes(select='action')))
        match_nodes = graphs_map[i].nodes(select='match')
        action_nodes = graphs_map[i].nodes(select='action')

        match_key_size = 0
        action_key_size = 0

        for node in match_nodes:
            match_key_size += graphs_map[i].node[node]['key_width']
    
        for node in action_nodes:
            action_key_size += graphs_map[i].node[node]['num_fields']
        
        print ("Branch " + str(i) + "match_usage, action_usage", match_key_size, action_key_size)
        

    

    print ("Common nodes")
    for i in range(0,3):
        for j in range(i+1,4):
            print ("Common nodes mapping",i, j, len(common_nodes_mapping[i][j]))

