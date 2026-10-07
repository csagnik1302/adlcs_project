import networkx as nx
import matplotlib.pyplot as plt


def view_graphml(file_path):
    gr=nx.read_graphml(file_path)
    nx.draw(gr)
    plt.show()


def inspect_graphml(file_path):
    
    graph=nx.read_graphml(file_path)
    n_nodes, n_edges=graph.number_of_nodes(), graph.number_of_edges()
    