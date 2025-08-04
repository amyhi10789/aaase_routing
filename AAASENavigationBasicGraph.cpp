// AAASENavigationBasicGraph.cpp : This file contains the 'main' function. Program execution begins and ends there.
//

#include <iostream>
#include <vector>
#include <fstream>
#include <cmath>

using namespace std;

typedef long long int ll;

struct Road {
    double weight;
    int startID;
    int endID;
};

int intersectionCount;

vector<vector<Road>> cityMap;
vector<vector<string>> intersectionRoads;
vector<double> intersectionLatitudes;
vector<double> intersectionLongitudes;
const int earthRadius = 6378137;
const double pi = 2 * acos(0.0);

bool isConnected(int i, int j) {
    for (auto road1 : intersectionRoads[i]) {
        for (auto road2 : intersectionRoads[j]) {
            if (road1 == road2) {
                return true;
            }
        }
    }
    return false;
}

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
    return earthRadius * c;
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

int main()
{
    ios::sync_with_stdio(false);
    cin.tie(0);

    cin >> intersectionCount;

    cout << intersectionCount << endl;

    cityMap.resize(intersectionCount);
    intersectionRoads.resize(intersectionCount);
    intersectionLatitudes.resize(intersectionCount);
    intersectionLongitudes.resize(intersectionCount);

    double x;
    double y;

    string curRoadName;
    char curchar;
    Road curRoad;

    for (int i = 0; i < intersectionCount; i++) {
        cin >> x >> y;

        if (x > 0) {
            x = -x;
        }
        x = convertToLongitude(x);
        y = convertToLatitude(y);
     //   printCords(x, y);

        string curRoadName = "";
        char curChar;

        intersectionLatitudes[i] = y;
        intersectionLongitudes[i] = x;

        while (true) {
            cin >> curChar;

            if (curChar == '&') {
                intersectionRoads[i].push_back(curRoadName);
                curRoadName = "";
                continue;
            }
            if (curChar == '-') {
                intersectionRoads[i].push_back(curRoadName);
                break;
            }
            curRoadName += curChar;
        }

        for (auto r : intersectionRoads[i]) {
     //       cout << r << " ";
        }
      //  cout << endl;
    }

    for (int i = 0; i < intersectionCount; i++) {
        for (int j = 0; j < intersectionCount; j++) {
            if (i == j) {
                continue;
            }
            if (isConnected(i, j)) {
                double weight = getDistance(intersectionLatitudes[i],
                    intersectionLongitudes[i],
                    intersectionLatitudes[j],
                    intersectionLongitudes[j]);

                curRoad.weight = weight;
                curRoad.startID = i;
                curRoad.endID = j;
                cityMap[i].push_back(curRoad);

            }
        }
    }
}
