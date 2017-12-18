
import importlib
import sys

from schedule_dag_for_generic_branch import ScheduleDAG


if __name__ == "__main__":
    
    branch = {}
    graphs_map = {}
    total_branch = importlib.import_module(sys.argv[1], "*")
    hw_spec = importlib.import_module(sys.argv[2], "*")
    latency_spec = importlib.import_module(sys.argv[3], "*")
    branch_count = int(sys.argv[4])

    for i in range(0,branch_count):
        branch[i] = importlib.import_module(sys.argv[i+5], "*")
        graphs_map[i] = ScheduleDAG()
        graphs_map[i].create_dag(branch[i].nodes, branch[i].edges, latency_spec)

    total_graph = ScheduleDAG()
    total_graph.create_dag(total_branch.nodes, total_branch.edges, latency_spec)

    branch_match_nodes = {}
    branch_action_nodes = {}
    total_branch_match_nodes = total_graph.nodes(select='match')
    total_branch_action_nodes = total_graph.nodes(select='action')

    for i in range(0, branch_count):
        branch_match_nodes[i] = graphs_map[i].nodes(select='match')
        branch_action_nodes[i] = graphs_map[i].nodes(select='action')
       # print(len(branch_match_nodes[i]), len(branch_match_nodes[i]))

    common_match_nodes = []
    common_action_nodes = []

    for node in total_branch_match_nodes:
        flag = 0

        for i in range(0, branch_count):
            if node in branch_match_nodes[i]:
                flag += 1
        
        if flag == branch_count:
            common_match_nodes.append(node)
    

    for node in total_branch_action_nodes:
        flag = 0

        for i in range(0, branch_count):
            if node in branch_action_nodes[i]:
                flag += 1
        
        if flag == branch_count:
            common_action_nodes.append(node)


    
    branch_unique_match_nodes = {}
    branch_unique_action_nodes = {}

    for i in range(0, branch_count):
        branch_unique_match_nodes[i] = []
        for node in branch_match_nodes[i]:
            if node not in common_match_nodes:
                branch_unique_match_nodes[i].append(node)
    

    for i in range(0, branch_count):
        branch_unique_action_nodes[i] = []
        for node in branch_action_nodes[i]:
            if node not in common_action_nodes:
                branch_unique_action_nodes[i].append(node)
    
    for i in range(0, branch_count):
        print("branch ", i)
        m_u_nodes = len(branch_unique_match_nodes[i])
        m_b_nodes = len(total_branch_match_nodes)
        p_nodes = float(m_u_nodes) *100 / float(m_b_nodes)

        print("Unique Match Nodes, Total_match Nodes, Percentage ", m_u_nodes, m_b_nodes, p_nodes)
        #print(branch_unique_match_nodes[i])

        a_u_nodes = len(branch_unique_action_nodes[i])
        a_b_nodes = len(total_branch_action_nodes)
        p_nodes = float(a_u_nodes) *100 / float(a_b_nodes)

        print("Unique Action Nodes, Total action Nodes, percentage", a_u_nodes, a_b_nodes, p_nodes)
        #print(branch_unique_action_nodes[i])

        p_nodes = float(a_u_nodes + m_u_nodes ) *100 / float(a_b_nodes + m_b_nodes)
        print("Total percentage",  p_nodes)
    


    


    



    


