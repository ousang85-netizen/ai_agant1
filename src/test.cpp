


size_t callback(void *data, size_t sz, size_t num, string *str) {
   size_t totalSize = sz * num;
   str.append((char*)data, totalSize);
   return totalSize;
}

struct point {
  int x;
  int y;
  wchar_t c;
};

int DecodeGoogleDoc(string &url) {
  CURL *curl;
  CURLcode res;
  string buffer;
  int retv = 0;
  
  curl = curl_easy_init();
  if (curl) {
    cur_easy_setopt(curl, CUROPT_URL, url.c_str());
    cur_easy_setopt(curl, CUROPT_FOLLOWLOCATION, 1L);
    cur_easy_setopt(curl, CUROPT_WRITEFUNCTION, callback);
    cur_easy_setopt(curl, CUROPT_WRITEDATA, &buffer);
    
    res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
      cout << "read google doc failed:" << curl_easy_strerror(res) << endl;
      retv = -1;
    } else {
      // now decode the string read from google doc 
      istringstream stream(buffer);
      string line; 
      vector<point> points;      

      while(getline(stream, line)) {
        point cur;
        if (sscanf(line.c_str(), L"%d %lc %d", &cur.x, &cur.c, &cur.y) != 3) {
          //wrong format, ignore this row
          continue;
        } else {
          points.push_back(cur);
        }
      }
      
      // sort the points so that it started at left to right, top to down order
      sort(points.begin(), points.end());

      // now print char by its order after sorted
      int curx = 0, cury = 0;
      for (int i = 0; i < points.size(); i++) {
        if (points[i].x != curx) {
          while(curx < points[i].x) {
            cout << endl;
            curx++;
          }
          cury = 0;
        } 
        while(cury < points[i].y) {
          cout << " ";
          cury++;
        }
      }
    }
  } else {
    retv = -1;
  }
  return retv;
}

int main() {

    string url = "https://docs.google.com/document/d/e/2PACX-1vSvM5gDlNvt7npYHhp_XfsJvuntUhq184By5xO_pA4b_gCWeXb6dM6ZxwN8rE6S4ghUsCj2VKR21oEP/pub";
    DecodeGoogleDoc(url);

    return 0;
}