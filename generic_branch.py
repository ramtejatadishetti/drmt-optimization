import collections
import importlib
import math
import sys
from itertools import *

import networkx as nx
from gurobipy import *

from printers import *
from schedule_dag_for_generic_branch import ScheduleDAG
import pprint as pp
from solution import Solution

BRANCH1_SPEC_FILE = 'ipv4_cdffdcombined'
BRANCH2_SPEC_FILE = 'ipv6_fdkjfdcombined'
HW = 'large_hwfd'
LATENCY = 'drmt_fdlatencies'

def get_total_unique_nodes(graphs_map, branch_count):
    unique_node_list = [] 
    for i in range(0, branch_count):
        graph_nodes = graphs_map[i].nodes()
        for j in range(0, len(graph_nodes)):
            if graph_nodes[j] not in unique_node_list:
                unique_node_list.append(graph_nodes[j])

    return unique_node_list

def get_unique_edges_and_delays(graphs_map, branch_count):
    edges = []
    edge_delays = {}

    for i in range(0, branch_count):
        graph_edges = graphs_map[i].edges()
        for (u,v) in graph_edges:
            if (u,v) not in edges:
                edges.append((u,v))
                edge_delays[(u,v)] = graphs_map[i].edge[u][v]['delay']
            
            else:
                if graphs_map[i].edge[u][v]['delay'] > edge_delays[(u,v)] :
                    edge_delays[(u,v)] = graphs_map[i].edge[u][v]['delay']
    
    return edges, edge_delays


def model_ilp(graphs_map, hw_spec, period, minute_limit):

    max_crit_path_len = 0
    branch_count = len(graphs_map)

    for i in range(0, branch_count):
        cpath, cplat = graphs_map[i].critical_path()
        if(cplat > max_crit_path_len):
            max_crit_path_len = cplat

    Q_MAX = int(math.ceil(1.5 * max_crit_path_len / period))
    T = period

    unique_node_list = graphs_map[branch_count-1].nodes()

    total_edges = graphs_map[branch_count-1].edges()

    m = Model()
    m.setParam("LogToConsole", 0)

    t = m.addVars(unique_node_list, lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="t")

    qr  = m.addVars(list(itertools.product(unique_node_list, range(Q_MAX), range(T))), vtype=GRB.BINARY, name="qr")

    any_match = m.addVars(list(itertools.product(range(Q_MAX), range(T))), vtype=GRB.BINARY, name = "any_match")
    any_action = m.addVars(list(itertools.product(range(Q_MAX), range(T))), vtype=GRB.BINARY, name = "any_action")

    length = m.addVar(lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="length")

    m.setObjective(length, GRB.MINIMIZE)

    m.addConstrs((t[v]  <= length for v in unique_node_list), "constr_length_is_max")

    m.addConstrs((sum(qr[v, q, r] for q in range(Q_MAX) for r in range(T)) == 1 for v in unique_node_list),\
                     "constr_unique_quotient_remainder")
    
    m.addConstrs((t[v] == \
                      sum(q * qr[v, q, r] for q in range(Q_MAX) for r in range(T)) * T + \
                      sum(r * qr[v, q, r] for q in range(Q_MAX) for r in range(T)) \
                      for v in unique_node_list), "constr_division")
    

    
    m.addConstrs((t[v] - t[u] >= graphs_map[branch_count-1].edge[u][v]['delay'] for (u,v) in total_edges),\
                     "constr_dag_dependencies")
    

    cond_nodes = graphs_map[branch_count-1].nodes(select='condition')


    for i in range(0, branch_count-1):
        match_nodes = graphs_map[i].nodes(select='match')
        action_nodes = graphs_map[i].nodes(select='action')
        total_action_nodes_per_branch = []
        total_action_nodes_per_branch_fields = {}

        for j in range(0, len(cond_nodes)):
            if cond_nodes[j] not in total_action_nodes_per_branch:
                total_action_nodes_per_branch.append(cond_nodes[j])
                total_action_nodes_per_branch_fields[cond_nodes[j]] = graphs_map[branch_count-1].node[cond_nodes[j]]['num_fields']

        for j in range(0, len(action_nodes)):
            if action_nodes[j] not in total_action_nodes_per_branch:
                total_action_nodes_per_branch.append(action_nodes[j])
                total_action_nodes_per_branch_fields[action_nodes[j]] = graphs_map[i].node[action_nodes[j]]['num_fields']
        
        m.addConstrs((sum(math.ceil((1.0 * graphs_map[i].node[v]['key_width']) / hw_spec.match_unit_size) * qr[v, q, r]\
                      for v in match_nodes for q in range(Q_MAX))\
                      <= hw_spec.match_unit_limit for r in range(T)),\
                      "constr_match_units_" + str(i))
    
        m.addConstrs((sum(total_action_nodes_per_branch_fields[v] * qr[v, q, r]\
                      for v in total_action_nodes_per_branch for q in range(Q_MAX))\
                      <= hw_spec.action_fields_limit for r in range(T)),\
                      "constr_action_fields_" + str(i))
        
    all_branch_match_nodes = graphs_map[branch_count-1].nodes(select='match')
    all_branch_cond_nodes = graphs_map[branch_count-1].nodes(select='condition')
    all_branch_alu_nodes = graphs_map[branch_count-1].nodes(select='action')

    all_branch_action_nodes = all_branch_alu_nodes + all_branch_cond_nodes

    m.addConstrs((sum(qr[v, q, r] for v in all_branch_match_nodes) <= (len(all_branch_match_nodes) * any_match[q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_match1_")
        
    m.addConstrs((sum(qr[v, q, r] for v in all_branch_action_nodes) <= (len(all_branch_action_nodes) * any_action[q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_action1_")

    m.addConstrs((sum(any_match[q, r] for q in range(Q_MAX)) <= hw_spec.match_proc_limit\
                      for r in range(T)), "constr_match_proc_")
    m.addConstrs((sum(any_action[q, r] for q in range(Q_MAX)) <= hw_spec.action_proc_limit\
                      for r in range(T)), "constr_action_proc_")


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
    ops_at_time = {}
    ops_on_ring = {}

    for i in range(0, branch_count):
        time_of_op[i] = {}
        ops_at_time[i] = collections.defaultdict(list)
        ops_on_ring[i] = collections.defaultdict(list)

        node_list = graphs_map[i].nodes() 
        for v in node_list:
            tv = int(t[v].x)
            time_of_op[i][v] = tv
            ops_at_time[i][tv].append(v)
    
    final_solution_list = {}
    for i in range(0, branch_count):
        final_solution_list[i] = Solution()
        
        for pd in range(T):
            final_solution_list[i].match_key_usage[pd] = 0
            final_solution_list[i].action_fields_usage[pd] = 0
            final_solution_list[i].match_units_usage[pd] = 0
            final_solution_list[i].match_proc_set[pd] = set()
            final_solution_list[i].match_proc_usage[pd] = 0
            final_solution_list[i].action_proc_usage[pd] = 0
            final_solution_list[i].action_proc_set[pd] = set()
    
    for i in range(0, branch_count):
        node_list = graphs_map[i].nodes()

        for node in node_list:
            k = time_of_op[i][node] / period
            r = time_of_op[i][node] % period

            ops_on_ring[i][r].append('p[%d].%s' % (k,node))

            if graphs_map[i].node[node]['type'] == 'match':
                final_solution_list[i].match_key_usage[r] += graphs_map[i].node[node]['key_width']
                final_solution_list[i].match_units_usage[r] += math.ceil((1.0 * graphs_map[i].node[node]['key_width'])/ hw_spec.match_unit_size)
                final_solution_list[i].match_proc_set[r].add(k)
                final_solution_list[i].match_proc_usage[r] = len(final_solution_list[i].match_proc_set[r])

            else:
                final_solution_list[i].action_fields_usage[r] = graphs_map[i].node[node]['num_fields']
                final_solution_list[i].action_proc_set[r].add(k)
                final_solution_list[i].action_proc_usage[r]  = len(final_solution_list[i].action_proc_set[r])
        
        final_solution_list[i].length = length
        final_solution_list[i].ops_at_time = ops_at_time[i]
        final_solution_list[i].time_of_op = time_of_op[i]
        final_solution_list[i].ops_on_ring = ops_on_ring[i]

    return final_solution_list

if __name__ == "__main__":
    # Read specification for each branch
    branch_spec = []

    if (len(sys.argv) <= 4):
        print ("Usage: ", sys.argv[0], " <HW file> <latency file> <time limit in mins> <binary_up_limit> <DAG files> ")
        exit(1)
    else:

        hw_spec = importlib.import_module(sys.argv[1], "*")
        latency_spec = importlib.import_module(sys.argv[2], "*")
        minute_limit = int(sys.argv[3])
        binary_up_limit = int(sys.argv[4])

        for i in range(5,len(sys.argv)):
           branch_spec.append(importlib.import_module(sys.argv[i], "*"))

    branch_count = len(branch_spec)


    for i in range(0, branch_count):
        branch_spec[i].action_fields_limit = hw_spec.action_fields_limit
        branch_spec[i].match_unit_limit = hw_spec.match_unit_limit
        branch_spec[i].match_unit_size = hw_spec.match_unit_size
        branch_spec[i].action_proc_limit = hw_spec.action_proc_limit
        branch_spec[i].match_proc_limit = hw_spec.match_proc_limit    


    # Create graphs for all branches
    graphs_map = {}

    for i in range(0, branch_count):
        graphs_map[i] = ScheduleDAG()
        graphs_map[i].create_dag(branch_spec[i].nodes, branch_spec[i].edges, latency_spec)


    match_key_size = {}
    for i in range(0, branch_count):
        print("Branch " + str(i) + " nodes length", len(graphs_map[i].nodes()))
        print("Branch " + str(i) + " match nodes length", len(graphs_map[i].nodes(select='match')))
        print("Branch " + str(i) + " action nodes length", len(graphs_map[i].nodes(select='action')))
        print("Branch " + str(i) + " condition nodes length", len(graphs_map[i].nodes(select='condition')))   
     
        match_nodes = graphs_map[i].nodes(select='match')
        action_nodes = graphs_map[i].nodes(select='action')
        condition_nodes = graphs_map[i].nodes(select='condition')

        match_key_size = 0
        action_key_size = 0

        for node in match_nodes:
            match_key_size += graphs_map[i].node[node]['key_width']
    
        for node in action_nodes:
            action_key_size += graphs_map[i].node[node]['num_fields']
        
        for node in condition_nodes:
            action_key_size += graphs_map[i].node[node]['num_fields']
        
        print ("Branch " + str(i) + " match_usage, action_usage", match_key_size, action_key_size)
    




    tpt_upper_bound = 0
    tpt_lower_bound = 0.01

    for i in range(0, branch_count-1):
        print ('{:*^80}'.format(' Input DAG-' + str(i)))
        tpt_bound1 = print_problem(graphs_map[i], hw_spec)
        print('\n\n')

        if tpt_bound1 > tpt_upper_bound :
            tpt_upper_bound = tpt_bound1
    
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

        soln = model_ilp(graphs_map, hw_spec, period, minute_limit)

        if (soln):
            last_good_period = period
            last_good_solution = soln
            high = period - 1
        else:
            low = period + 1


    for i in range(0, branch_count):
        print ("branch_" + str(i) + "schedule")
        print ('{:*^80}'.format(' scheduling period on one processor'))
        print (timeline_str(last_good_solution[i].ops_at_time, white_space=0, timeslots_per_row=4),'\n\n')
    
        print ('{:*^80}'.format('p[u] is packet from u scheduling periods ago'))
        print (timeline_str(last_good_solution[i].ops_on_ring, white_space=0, timeslots_per_row=4), '\n\n')

        
        print ('Match units usage (max = %d units) on one processor' % hw_spec.match_unit_limit)
        print (timeline_str(last_good_solution[i].match_units_usage, white_space=0, timeslots_per_row=16))

        print ('Action fields usage (max = %d fields) on one processor' % hw_spec.action_fields_limit)
        print (timeline_str(last_good_solution[i].action_fields_usage, white_space=0, timeslots_per_row=16))

        print ('Match packets (max = %d match packets) on one processor' % hw_spec.match_proc_limit)
        print (timeline_str(last_good_solution[i].match_proc_usage, white_space=0, timeslots_per_row=16))

        print ('Action packets (max = %d action packets) on one processor' % hw_spec.action_proc_limit)
        print (timeline_str(last_good_solution[i].action_proc_usage, white_space=0, timeslots_per_row=16))
    