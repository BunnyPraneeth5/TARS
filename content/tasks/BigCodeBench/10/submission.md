import numpy as np
import itertools
import random
import statistics

def task_func(T1, RANGE=100):
    """
    Convert elements in 'T1' to integers and create a list of random integers.
    The size of the list is the sum of the integers in `T1`.
    Calculate and return the mean, median, and mode of the list.

    Args:
        T1 (list): A list containing elements convertible to integers.
        RANGE (int): The upper limit for the random integers generated (inclusive,
                     meaning integers will be between 0 and RANGE). Defaults to 100.

    Returns:
        tuple: A tuple containing the mean, median, and mode of the generated list
               of random integers. The mean and median are floats, and the mode is an integer.

    Raises:
        statistics.StatisticsError: If T1 is empty, or if the generated list of
                                    random integers is empty (due to sum of T1 elements being 0),
                                    which leads to an empty dataset for statistics calculations.
    """
    if not T1:
        raise statistics.StatisticsError("T1 cannot be empty.")

    # Convert elements in T1 to integers and calculate their sum
    # This sum determines the size of the list of random integers
    list_size = sum(int(x) for x in T1)

    # Create a list of random integers.
    # The integers are generated between 0 and RANGE (inclusive).
    random_list = [random.randint(0, RANGE) for _ in range(list_size)]

    # Calculate mean, median, and mode of the generated list.
    # If 'random_list' is empty (i.e., list_size was 0), these functions will raise
    # a statistics.StatisticsError, which is consistent with the problem's
    # error handling for empty datasets.
    mean_val = statistics.mean(random_list)
    median_val = statistics.median(random_list)
    mode_val = statistics.mode(random_list)

    # Return the results as a tuple.
    # statistics.mean and statistics.median return floats.
    # statistics.mode returns the type of the elements, which are integers here.
    return (mean_val, median_val, mode_val)
