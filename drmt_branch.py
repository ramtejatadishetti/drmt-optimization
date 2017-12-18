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
    if (len(sys.argv) != 7):
        print ("Usage: ", sys.argv[0], " <DAG file1> <DAG file2>  <HW file> <latency file> <time limit in mins> <binary_up_limit>")
        exit(1)
    elif (len(sys.argv) == 7):
        BRANCH1_SPEC_FILE  = sys.argv[1]
        BRANCH2_SPEC_FILE  = sys.argv[2]
        HW = sys.argv[3]
        LATENCY = sys.argv[4]
        minute_limit = int(sys.argv[5])
        binary_up_limit = int(sys.argv[6])

    branch1_spec = importlib.import_module(BRANCH1_SPEC_FILE, "*")
    branch2_spec = importlib.import_module(BRANCH2_SPEC_FILE, "*")
    hw_spec = importlib.import_module(HW, "*")
    latency_spec = importlib.import_module(LATENCY, "*")


    branch1_spec.action_fields_limit = hw_spec.action_fields_limit
    branch1_spec.match_unit_limit = hw_spec.match_unit_limit
    branch1_spec.match_unit_size = hw_spec.match_unit_size
    branch1_spec.action_proc_limit = hw_spec.action_proc_limit
    branch1_spec.match_proc_limit = hw_spec.match_proc_limit    

    branch2_spec.action_fields_limit = hw_spec.action_fields_limit
    branch2_spec.match_unit_limit = hw_spec.match_unit_limit
    branch2_spec.match_unit_size = hw_spec.match_unit_size
    branch2_spec.action_proc_limit = hw_spec.action_proc_limit
    branch2_spec.match_proc_limit = hw_spec.match_proc_limit

    # Create graphs for both branches
    G1 = ScheduleDAG()
    G2 = ScheduleDAG()
    G1.create_dag(branch1_spec.nodes, branch1_spec.edges, latency_spec)
    G2.create_dag(branch2_spec.nodes, branch2_spec.edges, latency_spec)

    # Group common nodes
    common_nodes_mapping = get_common_nodes(G1, G2)
    #print (common_nodes_mapping)
    print ("Branch1 - nodes", len(G1.nodes()) )
    print ("Branch1 - match nodes", len(G1.nodes(select='match')))
    
    match_nodes = G1.nodes(select='match')
    action_nodes = G1.nodes(select='action')
     
    match_key_size = 0
    action_key_size = 0

    for node in match_nodes:
        match_key_size += G1.node[node]['key_width']
    
    for node in action_nodes:
        action_key_size += G1.node[node]['num_fields']
    
    print ("match_usage, action_usage", match_key_size, action_key_size)

    print ("Branch1 - action nodes", len(G1.nodes(select='action')))

    print ("Branch2 - nodes", len(G2.nodes()) )
    print ("Branch2 - match nodes", len(G2.nodes(select='match')))
    print ("Branch2 - action nodes", len(G2.nodes(select='action')))


    match_nodes = G2.nodes(select='match')
    action_nodes = G2.nodes(select='action')
     
    match_key_size = 0
    action_key_size = 0

    for node in match_nodes:
        match_key_size += G2.node[node]['key_width']
    
    for node in action_nodes:
        action_key_size += G2.node[node]['num_fields']
    
    print ("match_usage, action_usage", match_key_size, action_key_size)

    print ("Common nodes", len(common_nodes_mapping))
    
    # get esitimates on upperbound, lowerbound for number of periods
    print ('{:*^80}'.format(' Input DAG1 '))
    tpt_bound1 = print_problem(G1, branch1_spec)
    print ('\n\n')

    print ('{:*^80}'.format(' Input DAG2 '))
    tpt_bound2 = print_problem(G2, branch2_spec)
    print ('\n\n')

    tpt_lower_bound = 0.01
    if tpt_bound1 > tpt_bound2 :
        tpt_upper_bound = tpt_bound1
    else :
        tpt_upper_bound = tpt_bound2
    
    
    period_lower_bound = int(math.ceil((1.0) / tpt_upper_bound))
    period_upper_bound = int(math.ceil((1.0) / tpt_lower_bound))
    
    period = period_upper_bound
    last_good_solution = None
    last_good_period   = None

    if period_upper_bound > binary_up_limit :
        period_upper_bound = binary_up_limit
  
    print ('Searching between limits ', period_lower_bound, ' and ', period_upper_bound, ' cycles')
    low = period_lower_bound
    high = period_upper_bound
    while (low <= high):
        assert(low > 0)
        assert(high > 0)
        period = int(math.ceil((low + high)/2.0))
        print ('\nperiod =', period, ' cycles')
        print ('{:*^80}'.format(' Scheduling DRMT '))
        solution = model_ilp(G1, G2, common_nodes_mapping, branch1_spec, branch2_spec, period, minute_limit)

        if (solution):
            last_good_period   = period
            last_good_solution = solution
            high = period - 1
        else:
            low  = period + 1

    print ('{:*^80}'.format(' scheduling period on one processor'))
    print (timeline_str(last_good_solution.ops_at_time, white_space=0, timeslots_per_row=4),'\n\n')
    
    print ('{:*^80}'.format('p[u] is packet from u scheduling periods ago'))
    print (timeline_str(last_good_solution.ops_on_ring, white_space=0, timeslots_per_row=4), '\n\n')

    print ('{:*^80}'.format(' Branch1 stats'))
    print ('Match units usage (max = %d units) on one processor' % branch1_spec.match_unit_limit)
    print (timeline_str(last_good_solution.match_units_usage1, white_space=0, timeslots_per_row=16))

    print ('Action fields usage (max = %d fields) on one processor' % branch1_spec.action_fields_limit)
    print (timeline_str(last_good_solution.action_fields_usage1, white_space=0, timeslots_per_row=16))

    print ('Match packets (max = %d match packets) on one processor' % branch1_spec.match_proc_limit)
    print (timeline_str(last_good_solution.match_proc_usage1, white_space=0, timeslots_per_row=16))

    print ('Action packets (max = %d action packets) on one processor' % branch1_spec.action_proc_limit)
    print (timeline_str(last_good_solution.action_proc_usage1, white_space=0, timeslots_per_row=16))

    print ('{:*^80}'.format(' Branch2 stats'))
    print ('Match units usage (max = %d units) on one processor' % branch2_spec.match_unit_limit)
    print (timeline_str(last_good_solution.match_units_usage1, white_space=0, timeslots_per_row=16))

    print ('Action fields usage (max = %d fields) on one processor' % branch2_spec.action_fields_limit)
    print (timeline_str(last_good_solution.action_fields_usage2, white_space=0, timeslots_per_row=16))

    print ('Match packets (max = %d match packets) on one processor' % branch2_spec.match_proc_limit)
    print (timeline_str(last_good_solution.match_proc_usage2, white_space=0, timeslots_per_row=16))

    print ('Action packets (max = %d action packets) on one processor' % branch2_spec.action_proc_limit)
    print (timeline_str(last_good_solution.action_proc_usage2, white_space=0, timeslots_per_row=16))
