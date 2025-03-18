#include <iostream>
#include <vector>

using namespace std;

// 分区函数
int partition(vector<int>& arr, int low, int high) {
    int pivot = arr[high];  // 选择最后一个元素作为基准
    int i = low - 1;

    for (int j = low; j < high; j++) {
        if (arr[j] < pivot) {
            i++;
            swap(arr[i], arr[j]);  // 交换小于 pivot 的元素
        }
    }
    swap(arr[i + 1], arr[high]);  // 交换 pivot 到正确位置
    return i + 1;
}

// 快速排序
void quickSort(vector<int>& arr, int low, int high) {
    if (low < high) {
        int pi = partition(arr, low, high);  // 获取分区索引
        quickSort(arr, low, pi - 1);
        quickSort(arr, pi + 1, high);
    }
}

// 测试
int main() {
    vector<int> arr = {3, 6, 8, 10, 1, 2, 1};
    quickSort(arr, 0, arr.size() - 1);

    cout << "Sorted array: ";
    for (int num : arr) {
        cout << num << " ";
    }
    cout << endl;

    return 0;
}
