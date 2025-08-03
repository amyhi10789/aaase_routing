#include <bits/stdc++.h>
#define fastio ios::sync_with_stdio(0); cin.tie(0); cout.tie(0);
using namespace std;

int N, M; // N is number of nodes, M is number of edges

int start_node, end_node; // start and end nodes
vector<bool> visited; // shows which nodes we already visited
vector<int> shortest_path; //stores the shortest path starting from the start node
vector<vector<pair<int, int> > > adj; // the adjacency matrix. adj[a] gives a list of pairs such as {b, c} where b is the node it is connected to and c is the cost/danger of the edge

void dij () {
    priority_queue<pair<int, int>, vector<pair<int, int> >, greater<pair<int, int> > > pq; // the min priority queue
    pq.push({0, start_node}); // distance to the start node is 0. This is the base case

    while(!pq.empty()) { // run until we reach every node
        int node = pq.top().second; // old node
        int dist = pq.top().first; // distance to old node
        pq.pop();
        if (visited[node]) {
            continue;
        }
        visited[node] = true; // make sure we dont come back to this old node
        shortest_path[node] = dist; // initialize the distance 
        for (pair<int, int> new_data : adj[node]) { // go to the nodes the old node is connected to
            int child = new_data.first;
            int add_cost = new_data.second;
            if (!visited[child]) {
                pq.push({dist + add_cost, child});
            }
        }
    }


}

int main() {
    fastio;
    cin >> N >> M; // read in N and M

    // initialize the vectors and matricies
    visited = vector<bool>(N, false);
    shortest_path = vector<int> (N, INT_MAX);
    adj = vector<vector<pair<int, int> > > (N); 

    cin >> start_node >> end_node; // read in the start and end nodes
    for (int i = 0; i < M; i++) {
        int a, b, c; //a and b are the nodes, c is the crime.
        cin >> a >> b >> c; // read in the adjacency matrix
        adj[a].push_back({b, c});
        adj[b].push_back({a, c});
    }
    dij(); // run the main dijkstra algorithm
    cout << shortest_path[end_node] << '\n'; // print the shortest path to the end node
}