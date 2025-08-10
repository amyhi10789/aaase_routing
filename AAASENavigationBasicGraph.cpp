// AAASENavigationBasicGraph.cpp : This file contains the 'main' function. Program execution begins and ends there.
//

#include <iostream>
#include <vector>
#include <fstream>
#include <cmath>
#include <filesystem>
#include <string>
#include <map>
#include <set>
#include <algorithm>
#include <queue>

using namespace std;

typedef long long int ll;

int intersectionCount;

struct Road {
    int weight;
    int endIntersection;
    int crimeCount;
};

vector<vector<Road>> cityMap; // distance, endNode
vector<vector<string>> intersectionRoads;      
vector<double> intersectionLatitudes;
vector<double> intersectionLongitudes;
const int earthRadius = 6378137;
const double pi = 2 * acos(0.0);
map<string, vector<string>> roadAdj;
map<vector<string>, int> roadsToIntersection;
set<string> roads;
vector<int> crimeCount;

double getDistance(double lat1, double lon1,
    double lat2, double lon2)
{
    double dLat = (lat2 - lat1) *
        pi / 180.0;
    double dLon = (lon2 - lon1) *
        pi / 180.0;

    lat1 = (lat1)*pi / 180.0;
    lat2 = (lat2)*pi / 180.0;

    double a = pow(sin(dLat / 2), 2) +
        pow(sin(dLon / 2), 2) *
        cos(lat1) * cos(lat2);
    double c = 2 * asin(sqrt(a));
    return abs(earthRadius * c);
}

double convertToLongitude(double x) {
    return x / earthRadius * 180 / pi;
}
double convertToLatitude(double y) {
    return atan(sinh(y / earthRadius)) * 180 / pi;
}
void printCords(double x, double y) {
    cout << "latitude: " << x << "longitude: " << y << endl;
}
void printIntersection (int i) {
    for (int j = 0; j < intersectionRoads[i].size() - 1; j++) {
        cout << intersectionRoads[i][j] << " & ";
    }
    cout << intersectionRoads[i][intersectionRoads[i].size() - 1] << endl;

    //outFile.close();
}
void printVector (vector<string> v) {
    for (auto i : v) {
        cout << i << " ";
    }
    cout << endl;
}
void printIntersectingRoads (string road) {
    cout << "All roads intersecting with road " << road << ":";
    printVector(roadAdj[road]);
}

const int blankAscii = -39;

double getDistance (int i1, int i2) {
    return getDistance(intersectionLatitudes[i1], intersectionLongitudes[i1], 
    intersectionLatitudes[i2], intersectionLongitudes[i2]);
}

struct Crime {
    double latitude;
    double longitude;
};

int crimCnt = 0;
vector<Crime> crimes;

void initCrimes () {
    ifstream inFile("crimes.in");

    double lat;
    double lo;
    Crime curCrime;

    while (true) {
        inFile >> lat;

        if (lat == 0) {
            break;
        }
        inFile >> lo;

        curCrime.latitude = lat;
        curCrime.longitude = lo;

        crimes.push_back(curCrime);
    }
   // crimes.resize(5000);

    cout << "Crimes: " << crimes.size() << endl;
}
const int crimeDistanceToleranceMeters = 150;
const int crimeWeightPenalty = 100;
int getNearbyCrimes (int i) {
    if (i % 100 == 0) {
        cout << i << endl;
    }
    int cnt = 0;
    for (Crime c : crimes) {
        if (getDistance(c.latitude, c.longitude, 
            intersectionLatitudes[i], intersectionLongitudes[i]) < crimeDistanceToleranceMeters) {
            cnt++;
        }
    }
    return cnt;
}

void turnRoadIntoGraph (string curRoad) {
    int endpoint;
    int maxDistance = -1e9;
    int curIntersection = 0;
    int curDistance;
    int startIntersection = 0; // random arbitary node

    vector<string> curRoadList;
    curRoadList.push_back(curRoad);
    string r;
    vector<int> intersections;

   // cout << curRoad << " has " << roadAdj[curRoad].size() << "adj roads" << endl;

    for (int i = 0; i < roadAdj[curRoad].size(); i++) {
        r = roadAdj[curRoad][i];
        curRoadList.push_back(r);
        sort(curRoadList.begin(), curRoadList.end());
        curIntersection = roadsToIntersection[curRoadList];

        //cout << curIntersection << " ";
        // printVector(curRoadList);
        intersections.push_back(curIntersection);
        
        if (i == 0) {
            startIntersection = curIntersection;
            endpoint = curIntersection;
            curRoadList.clear();
            curRoadList.push_back(curRoad);
            continue;
        }
        curDistance = getDistance(startIntersection, curIntersection);
      //  cout << curRoad << ":" << curDistance << " " << maxDistance << endl;

        if (curDistance > maxDistance) {
            maxDistance = curDistance;
            endpoint = curIntersection;
        }

        curRoadList.clear();
        curRoadList.push_back(curRoad);
    }

    vector<pair<double, int>> distances;

    for (auto i : intersections) {
        if (i == endpoint) {
            continue;
        }
        distances.push_back({getDistance(endpoint, i), i});
    }
  //  cout << "endpoint for " << curRoad << ": is" << endpoint << endl;

    int prevNode = endpoint;
    Road edge;

    sort(distances.begin(), distances.end());

    const int maxTolerance = 1000;
    int curCrimes = 0;

    for (int i = 0; i < distances.size(); i++) {
        edge.endIntersection = distances[i].second;
        edge.crimeCount = crimeCount[edge.endIntersection];
        edge.weight = getDistance(prevNode, distances[i].second) + edge.crimeCount * crimeWeightPenalty;

        // block and continue
        if (edge.weight > maxTolerance) {
            prevNode = distances[i].second;
            continue;
        }
        cityMap[prevNode].push_back(edge);
        edge.weight -= edge.crimeCount * crimeWeightPenalty;
        
        edge.endIntersection = prevNode;
        edge.crimeCount = crimeCount[edge.endIntersection];
        edge.weight += edge.crimeCount * crimeWeightPenalty;
        cityMap[distances[i].second].push_back(edge);

        prevNode = distances[i].second;
    }
}

void findShortestPath (int startNode, int endNode) {
    priority_queue<vector<long long int>, vector<vector<long long int> >, greater<vector<long long int> > > pq; // the min priority queue, order is distance, the node and where the node came from.
    pq.push({0, startNode, startNode}); // distance to the start node is 0. This is the base case
    vector<bool> visited(intersectionCount); // shows which nodes we already visited
    vector<pair<int, double> > shortest_path(intersectionCount); //stores the shortest path starting from the start node
    while(!pq.empty()) { // run until we reach every node
        int node = pq.top()[1]; // old node
        int dist = pq.top()[0]; // distance to old node
        int came_from = pq.top()[2];
        cout << node << endl;
        pq.pop();
        if (visited[node]) {
            continue;
        }
        visited[node] = true; // make sure we dont come back to this old node
        shortest_path[node] = {dist, came_from}; // initialize the distance 
        for (Road new_data : cityMap[node]) { // go to the nodes the old node is connected to
            int child = new_data.endIntersection;
            int add_cost = new_data.weight;
            if (!visited[child]) {
                pq.push({dist + add_cost, child, node});
            }
        }
    }

    cout << shortest_path[endNode].first << '\n'; // print the shortest path to the end node
    
    vector<int> ans;
    int cur_node = endNode;
    while(cur_node != startNode) {
        ans.push_back(cur_node);
        cur_node = shortest_path[cur_node].second;
    }
    ans.push_back(startNode);
    ofstream outFile ("path.txt");

    for (int i = ans.size() - 1; i >= 1; i--) {
        outFile << intersectionLatitudes[ans[i]] << " " << intersectionLongitudes[ans[i]] << endl;
        printIntersection(ans[i]);
        cout << crimeCount[ans[i]] << endl;
    }
     outFile << intersectionLatitudes[endNode] << " " << intersectionLongitudes[endNode] << endl;
    printIntersection(endNode);
}

int main()
{
    ios::sync_with_stdio(false);
    cin.tie(0);

    ifstream inFile("intersections.in");

    if (inFile.is_open()) {
        cout << "opened successfully" << endl;
    }

    inFile >> intersectionCount;
    intersectionCount = 500;
    cout << intersectionCount << endl;

    cityMap.resize(intersectionCount);
    intersectionRoads.resize(intersectionCount);
    intersectionLatitudes.resize(intersectionCount);
    intersectionLongitudes.resize(intersectionCount);
    crimeCount.resize(intersectionCount);

    double x;
    double y;

    string curRoadName;
    char curchar;
    Road curRoad;

    string curInput;

    for (int i = 0; i < intersectionCount; i++) {
       // getline(inFile, curInput);

        string curX;
        string curY;

        inFile >> x >> y;

        if (x > 0) {
            x = -x;
        }
        if (x == 0) {
            cout << "failed at line " << i << endl;

            return 0;
        }
        x = convertToLongitude(x);
        y = convertToLatitude(y);
       // printCords(x, y);

        string curRoadName = "";
        string curRoads;
        char curChar;

        intersectionLatitudes[i] = y;
        intersectionLongitudes[i] = x;

        getline(inFile, curRoads);

        for (int j = 0; j < curRoads.length(); j++) {
            if (curRoads[j] - '0' == blankAscii) {
                continue;
            }
            if (curRoads[j] == ' ') {
                continue;
            }
            if (curRoads[j] == '&') {
                intersectionRoads[i].push_back(curRoadName);

                curRoadName = "";
                
                continue;
            }
            curRoadName += curRoads[j];
        }
        intersectionRoads[i].push_back(curRoadName);

        for (auto r : intersectionRoads[i]) {
            roads.insert(r);
         //   cout << r << " ";
        }
      //  cout << endl;

        for (int j = 0; j < intersectionRoads[i].size(); j++) {
            for (int x = j + 1; x < intersectionRoads[i].size(); x++) {
             //   cout << intersectionRoads[i][j] << " " << intersectionRoads[i][x] << endl;
                roadAdj[intersectionRoads[i][j]].push_back(intersectionRoads[i][x]);
                roadAdj[intersectionRoads[i][x]].push_back(intersectionRoads[i][j]);
            }
        }
    }
    initCrimes();

    for (int i = 0; i < intersectionCount; i++) {
        crimeCount[i] = getNearbyCrimes(i);
        sort(intersectionRoads[i].begin(), intersectionRoads[i].end());

        roadsToIntersection[intersectionRoads[i]] = i;
    }
    
    for (auto r : roads) {
        turnRoadIntoGraph(r);

      //  printIntersectingRoads(r);
    }
    // for (Road edge : cityMap[10]) {
    //     cout << edge.endIntersection << " ";
    // }
    // cout << endl;
    cout << "finding shortest path" << endl;
     findShortestPath(8, 25);
}
