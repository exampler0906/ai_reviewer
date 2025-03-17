def quick_sort(arr):
    if len(arr) <= 1:
        return arr  # 递归终止条件

    pivot = arr[len(arr) // 2]  # 选择中间元素作为基准
    left = [x for x in arr if x < pivot]  # 小于 pivot 的元素
    middle = [x for x in arr if x == pivot]  # 等于 pivot 的元素
    right = [x for x in arr if x > pivot]  # 大于 pivot 的元素
    

    return quick_sort(left) + middle + quick_sort(right)

# 测试
arr = [3, 6, 8, 10, 1, 2, 1]
sorted_arr = quick_sort(arr)
print("Sorted array:", sorted_arr)
