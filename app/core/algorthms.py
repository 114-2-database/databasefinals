import pandas as pd

def calculate_moving_average(data: pd.Series, window_size: int) -> pd.Series:
    """
    Calculate the moving average of a given data series.

    Parameters:
    data (pd.Series): The input data series.
    window_size (int): The size of the moving average window.

    Returns:
    pd.Series: The moving average of the input data series.
    """
    return data.rolling(window=window_size).mean()

if __name__ == "__main__":
    # Example usage
    data = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    window_size = 3
    moving_average = calculate_moving_average(data, window_size)
    print(moving_average)