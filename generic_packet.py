import math
from gurobipy import *
import sys
import importlib
from itertools import *
from schedule_dag import ScheduleDAG

def create_compund_graph(nodes, edges, burst_size):
    node_dict = {}
    edge_dict = {}

    for node in nodes:
        for packet_id in range(burst_size):
            node_name = str(packet_id) + "_" + str(node) 
            node_dict[node_name] = nodes[node]

    for edge_tuple in edges:
        for packet_id in range(burst_size):
            node0 = str(packet_id)+ "_" + str(edge_tuple[0])
            node1 = str(packet_id)+ "_" + str(edge_tuple[1])
            edge_dict[(node0, node1)]  = edges[edge_tuple]
    
    return node_dict, edge_dict


def get_node_name(node_name):
    return node_name[2:]

def get_packet_id_from_name(node_name):
    return int(node_name[0])

def get_nodes_per_packet(nodes, packet_id):
    node_list = []
    for node in nodes:
        if get_packet_id_from_name(node) == packet_id :
            node_list.append(node)
    
    return node_list


def model_ilp(graph_map, hw_spec, period, minute_limit, burst_size):

    if (period%burst_size != 0) :
        print("skipping if processor is not multiple of burst_size")
        exit(1)
    
    cpath, cplat = graph_map.critical_path()
    
    Q_MAX = int(math.ceil(1.5 * burst_size * cplat / period))
    T = period

    m = Model()
    m.setParam("LogToConsole", 0)

    node_list = graph_map.nodes()

    t = m.addVars(node_list, lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="t")
    qr  = m.addVars(list(itertools.product(node_list, range(Q_MAX), range(T))), vtype=GRB.BINARY, name="qr")

    any_match = {}
    any_action = {}

    for i in range(burst_size):
        any_match[i] = m.addVars(list(itertools.product(range(Q_MAX), range(T))), vtype=GRB.BINARY, name = "any_match_"+str(i))
        any_action[i] = m.addVars(list(itertools.product(range(Q_MAX), range(T))), vtype=GRB.BINARY, name = "any_action_"+str(i))


    length = m.addVar(lb=0, ub=GRB.INFINITY, vtype=GRB.INTEGER, name="length")

    m.setObjective(length, GRB.MINIMIZE)

    m.addConstrs((t[v]  <= length for v in node_list), "constr_length_is_max")

    m.addConstrs((sum(qr[v, q, r] for q in range(Q_MAX) for r in range(T)) == 1 for v in node_list),\
                     "constr_unique_quotient_remainder")
    
    m.addConstrs((t[v] == \
                      sum(q * qr[v, q, r] for q in range(Q_MAX) for r in range(T)) * T + \
                      sum(r * qr[v, q, r] for q in range(Q_MAX) for r in range(T)) \
                      for v in node_list), "constr_division")
    
    m.addConstrs((t[v] - t[u] >= graphs_map.edge[u][v]['delay'] for (u,v) in graph_map.edges()),\
                     "constr_dag_dependencies")
    
    match_nodes = graph_map.nodes(select='match')
    action_nodes = graph_map.nodes(select='action')

    m.addConstrs((sum(math.ceil((1.0 * graph_map.node[v]['key_width']) / hw_spec.match_unit_size) * qr[v, q, r]\
                      for v in match_nodes for q in range(Q_MAX))\
                      <= hw_spec.match_unit_limit for r in range(T)),\
                      "constr_match_units")

    # The action field resource constraint (similar comments to above)
    m.addConstrs((sum(graph_map.node[v]['num_fields'] * qr[v, q, r]\
                      for v in action_nodes for q in range(Q_MAX))\
                      <= hw_spec.action_fields_limit for r in range(T)),\
                      "constr_action_fields")

    
    for i in range(0,burst_size):
        match_nodes_per_packet = get_nodes_per_packet(match_nodes, i)
        action_nodes_per_packet = get_nodes_per_packet(action_nodes, i)

        m.addConstrs((sum(qr[v, q, r] for v in match_nodes_per_packet) <= (len(match_nodes_per_packet) * any_match[i][q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_match_"+str(i))
        
        m.addConstrs((sum(qr[v, q, r] for v in action_nodes_per_packet) <= (len(action_nodes_per_packet) * any_action[i][q, r]) \
                      for q in range(Q_MAX)\
                      for r in range(T)),\
                      "constr_any_action_"+str(i))
    


    m.addConstrs((sum(any_match[q, r] for q in range(Q_MAX)) <= hw_spec.match_proc_limit\
                      for r in range(T)), "constr_match_proc")





if __name__ == "__main__":

    if (len(sys.argv)) < 7:
        print ("Usage: ", sys.argv[0], " <DAGfile> <HW file> <latency file> <time limit in mins> <up_limit> <burst_size>")
        exit(1)
    else :
        input_spec = importlib.import_module(sys.argv[1], "*")
        hw_spec = importlib.import_module(sys.argv[2], "*")
        latency_spec = importlib.import_module(sys.argv[3], "*")
        minute_limit = int(sys.argv[4])
        seed = int(sys.argv[5])
        burst_size = int(sys.argv[6])

    input_spec.action_fields_limit = hw_spec.action_fields_limit
    input_spec.match_unit_limit = hw_spec.match_unit_limit
    input_spec.match_unit_size = hw_spec.match_unit_size
    input_spec.action_proc_limit = hw_spec.action_proc_limit
    input_spec.match_proc_limit = hw_spec.match_proc_limit

    graph_map = ScheduleDAG()

    
    t_nodes, t_edges = create_compund_graph(input_spec.nodes, input_spec.edges, burst_size)
    graph_map.create_dag(t_nodes, t_edges, latency_spec)
    print(graph_map.critical_path())
    print(len(graph_map.nodes()))

    last_good_soln = None
    last_good_period = None

    for period in range(seed+5, seed-5, -1):
        soln = model_ilp(graph_map, hw_spec, period, minute_limit, burst_size)

        if (soln):
            last_good_period = period
            last_good_soln = soln
        else:
            print("Infeasible soln")
    

    print ("branch_" + str(i) + "schedule")
    print ('{:*^80}'.format(' scheduling period on one processor'))
    print (timeline_str(last_good_solution.ops_at_time, white_space=0, timeslots_per_row=4),'\n\n')
    
    print ('{:*^80}'.format('p[u] is packet from u scheduling periods ago'))
    print (timeline_str(last_good_solution.ops_on_ring, white_space=0, timeslots_per_row=4), '\n\n')

        
    print ('Match units usage (max = %d units) on one processor' % hw_spec.match_unit_limit)
    print (timeline_str(last_good_solution.match_units_usage, white_space=0, timeslots_per_row=16))

    print ('Action fields usage (max = %d fields) on one processor' % hw_spec.action_fields_limit)
    print (timeline_str(last_good_solution.action_fields_usage, white_space=0, timeslots_per_row=16))

    print ('Match packets (max = %d match packets) on one processor' % hw_spec.match_proc_limit)
    print (timeline_str(last_good_solution.match_proc_usage, white_space=0, timeslots_per_row=16))

    print ('Action packets (max = %d action packets) on one processor' % hw_spec.action_proc_limit)
    print (timeline_str(last_good_solution.action_proc_usage, white_space=0, timeslots_per_row=16))
        








