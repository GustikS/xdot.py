import pygraphviz as pgv
import collections
import json

DEFAULT_JSON_FILE = "meta"
DEFAULT_RELATIVE_JSON_DIRECTORY = "templates/"

# This cluster name is sometimes over the whole graph, will be ignored
ROOT_CLUSTER = "root"

PARAMETERS_TAG = "parameters"
NESTED_TAG = "nested"
CONDITION_TAG = "condition"
SCOPE_TAG = "scopes"

MAIN_NODE_IDENTIFIER = "object_name"
INSERTED_NODE_GENERIC_NAME = "NEW_MODEL"

CLUSTER_EXITING_NODE_COLOR = "#CCCCFF"
NODE_SHAPE = "box"
PARAMETERS_ARROWHEAD = "ediamond"
NESTED_ARROWHEAD = "normal"


class VisualizationTool:

    def __init__(self, file_name=DEFAULT_JSON_FILE, content_src="", add_to="", existing_node=""):
        # subgraphs collection to draw clusters right
        self.subgraphs = collections.OrderedDict()
        # edges cannot be added on the go, as some node maybe referring to a different node, whose declaration is later
        self.edges_to_add_in_the_end = dict()
        # Node into which is new parameter inserted
        self.insert_parameter_into_node = add_to
        # new parameter reference to existing node
        self.existing_node_parameter = existing_node

        # Won't be needed if all nodes have unique id
        self.last_graph_node_id = 1

        self.file_name = file_name
        if self.file_name.endswith(".json"):
            self.file_name = file_name.replace(".json", "")

        content = content_src
        if content_src == "":
            with open(DEFAULT_RELATIVE_JSON_DIRECTORY + file_name + '.json', 'r') as content_file:
                content = content_file.read()
        self.json_text = json.loads(content)

        self.graph = pgv.AGraph(strict=False, directed=True)

    def visualize_template(self):
        name = self.get_modul_name(self.json_text)
        self.go_next(name, name, self.json_text, False, [])

        # Edges must be added at the end, as something can be referenced before its declaration
        for node_key in self.edges_to_add_in_the_end:
            for node in self.edges_to_add_in_the_end[node_key]:
                self.graph.add_edge(node_key, node, arrowhead=NESTED_ARROWHEAD)

        # We don't want to make cluster over the whole graph
        if ROOT_CLUSTER in self.subgraphs:
            del self.subgraphs[ROOT_CLUSTER]

        # Creating subgraphs that can be inside another subgraphs
        subgraphs_keys = list(self.subgraphs.keys())
        subgraphs_references = []
        for subgraph_key in subgraphs_keys:
            subgraph_to_insert_to = self.graph
            # Go through (mostly) bigger and outer subgraphs and check if this subgraph is part of other subgraph
            for bigger_subgraph_key in subgraphs_keys[::-1]:
                if subgraph_key in self.subgraphs[bigger_subgraph_key]:
                    subgraph_to_insert_to = subgraphs_references[subgraphs_keys.index(bigger_subgraph_key)]
                    break
            # CLUSTER in graphviz MUST START WITH NAME CLUSTER, otherwise it wont be displayed
            subgraph_to_insert_to.add_subgraph(self.subgraphs[subgraph_key], name=("cluster" + subgraph_key), label=subgraph_key)
            subgraphs_references.append(subgraph_to_insert_to.subgraphs()[-1])
            for subgraph_node in self.subgraphs[subgraph_key]:
                subgraph_to_insert_to.add_node(subgraph_node)

        for node in self.graph.nodes():
            node.attr['shape'] = NODE_SHAPE

        graph_result_dot = str(self.graph)
        self.graph.layout(prog='dot')
        self.graph.draw(self.file_name + ".dot")
        self.graph.draw(self.file_name + ".jpeg")

        # if inserting, json has been changed and need to be propagated back
        if self.insert_parameter_into_node != "":
            return graph_result_dot, self.json_text
        return graph_result_dot

    def go_next(self, root_node_json, node_name, node_json, is_cluster, subgraphs_roots):
        if self.insert_parameter_into_node != "" and self.insert_parameter_into_node == node_name:
            # More nodes can have same object name, referring to the one,
            # in case of just referring, they don't have other attributes
            if len(node_json.keys()) > 1:
                node_json = self.insert_new_reference(node_json)

        # Return if this tree continues
        if NESTED_TAG in node_json:
            self.process_nested(root_node_json, node_json[NESTED_TAG], is_cluster, subgraphs_roots)
            return True
        elif PARAMETERS_TAG in node_json:
            self.process_parameters(node_name, node_json[PARAMETERS_TAG], subgraphs_roots)
        return False

    def insert_new_reference(self, node):
        if self.existing_node_parameter == "":
            if PARAMETERS_TAG in node:
                parameters = node[PARAMETERS_TAG]
                parameters[INSERTED_NODE_GENERIC_NAME] = dict()
                parameters[INSERTED_NODE_GENERIC_NAME][MAIN_NODE_IDENTIFIER] = INSERTED_NODE_GENERIC_NAME
                parameters[INSERTED_NODE_GENERIC_NAME]["build_path"] = dict()
                parameters[INSERTED_NODE_GENERIC_NAME]["build_path"]["module_name"] = "xxxxx"
                parameters[INSERTED_NODE_GENERIC_NAME]["build_path"]["class_name"] = "xxxxx"
            else:
                node[PARAMETERS_TAG] = dict()
                node[PARAMETERS_TAG][INSERTED_NODE_GENERIC_NAME] = dict()
                node[PARAMETERS_TAG][INSERTED_NODE_GENERIC_NAME][MAIN_NODE_IDENTIFIER] = INSERTED_NODE_GENERIC_NAME
                node[PARAMETERS_TAG][INSERTED_NODE_GENERIC_NAME]["build_path"] = dict()
                node[PARAMETERS_TAG][INSERTED_NODE_GENERIC_NAME]["build_path"]["module_name"] = "xxxxx"
                node[PARAMETERS_TAG][INSERTED_NODE_GENERIC_NAME]["build_path"]["class_name"] = "xxxxx"
        else:
            if PARAMETERS_TAG in node:
                parameters = node[PARAMETERS_TAG]
                parameters[self.existing_node_parameter] = dict()
                parameters[self.existing_node_parameter][MAIN_NODE_IDENTIFIER] = self.existing_node_parameter
            else:
                node[PARAMETERS_TAG] = dict()
                node[PARAMETERS_TAG][self.existing_node_parameter] = dict()
                node[PARAMETERS_TAG][self.existing_node_parameter][MAIN_NODE_IDENTIFIER] = self.existing_node_parameter
        return node

    def process_nested(self, root_node_json, nested_json_array, is_cluster, subgraphs_roots):
        subgraphs_roots_clone = list(subgraphs_roots)
        subgraphs_roots_clone.append(root_node_json)
        last_node = None

        for node_json in nested_json_array:
            node_name = self.get_modul_name(node_json)
            if node_name == "":
                continue
            self.add_current_node_to_all_corresponding_subgraphs(subgraphs_roots_clone, node_name)
            if "output" in node_json:
                if node_name not in self.edges_to_add_in_the_end:
                    self.edges_to_add_in_the_end[node_name] = [node_json["output"]]
                else:
                    self.edges_to_add_in_the_end[node_name].append(node_json["output"])
            self.go_next(root_node_json, node_name, node_json, False, subgraphs_roots_clone)
            last_node = node_name

        # Last node in cluster highlight
        if is_cluster:
            self.graph.add_edge(last_node, root_node_json, arrowhead=PARAMETERS_ARROWHEAD)
            cluster_exiting_node = self.graph.get_node(last_node)
            cluster_exiting_node.attr['style'] = 'filled'
            cluster_exiting_node.attr['fillcolor'] = CLUSTER_EXITING_NODE_COLOR

    def process_parameters(self, root_node, node_json_parameters, subgraphs_roots):
        for key in node_json_parameters:
            node = node_json_parameters[key]
            name = ""
            if isinstance(node, dict):
                name = self.get_modul_name(node)
                if name == "":
                    continue
                # find out if this tree continue with nested block (which is only single-key dictionary as json)
                if self.go_next(root_node, name, node, True, subgraphs_roots):
                    continue
                self.add_current_node_to_all_corresponding_subgraphs(subgraphs_roots, name)
                self.graph.add_edge(name, root_node, arrowhead=PARAMETERS_ARROWHEAD)
            if key == CONDITION_TAG:
                first_cond = (node[PARAMETERS_TAG][SCOPE_TAG])[0][MAIN_NODE_IDENTIFIER]
                second_cond = (node[PARAMETERS_TAG][SCOPE_TAG])[1][MAIN_NODE_IDENTIFIER]
                self.graph.add_edge(first_cond, name, arrowhead=PARAMETERS_ARROWHEAD)
                self.graph.add_edge(second_cond, name, arrowhead=PARAMETERS_ARROWHEAD)

    def get_modul_name(self, node):
        name = str(self.last_graph_node_id)
        if MAIN_NODE_IDENTIFIER in node:
            name = node[MAIN_NODE_IDENTIFIER]
        # Should not be needed if all nodes have unique identifier, kept for compatibility with example json
        elif "object_type" in node:
            name = node["object_type"] + "_" + str(self.last_graph_node_id)
            self.last_graph_node_id += 1
        elif "build_path" in node:
            name = node["build_path"]["class_name"] + "_" + str(self.last_graph_node_id)
            self.last_graph_node_id += 1
        else:
            return ""
        return name

    def add_current_node_to_all_corresponding_subgraphs(self, subgraphs_roots, name):
        for subgraph_root in subgraphs_roots:
            if subgraph_root not in self.subgraphs:
                self.subgraphs[subgraph_root] = [name]
            else:
                if name not in self.subgraphs[subgraph_root]:
                    self.subgraphs[subgraph_root].append(name)


if __name__ == "__main__":
    visualization_tool = VisualizationTool()
    visualization_tool.visualize_template()