import pandas as pd
import numpy as np
import gc
import datetime
# import re


def read_case_0(read_filepath, calendar_filepath):
    """Reads data for case 0

    Args:
        read_filepath (str): Existing location of the data file.
        calendar_filepath (str): Existing location of the calendar file.
            Required for reading.

    Returns:
        pandas.DataFrame: A dataframe with the loaded data.

    Example usage:
    >>> df = read_case_0('data.csv', 'calendar.csv')

    """

    # read the data file and the calendar
    df = pd.read_csv(read_filepath)
    calendar = pd.read_csv(calendar_filepath)

    # Drop some columns
    # Hierarchy is defined as:
    # State -> Store -> Category -> Department -> Item
    to_drop = ["item_id", "dept_id", "cat_id", "store_id", "state_id"]
    df = df.drop(to_drop, axis=1)

    # Modify the id and set it as index
    df["id"] = ["_".join(d.split("_")[:-1]) for d in df["id"].values]
    df = df.rename(columns={"id": "unique_id"})
    df = df.set_index("unique_id")

    # Prepare the dates from the calendar
    dates = calendar[["d", "date"]]

    # find the total days
    total_days = df.shape[1]
    dates = dates.iloc[:total_days]["date"].values

    # Replace on the columns
    df.columns = dates

    # Convert to datetime
    df.columns = pd.to_datetime(df.columns)

    # drop columns with only zeros
    df = df.loc[~(df == 0).all(axis=1)]

    return df


def read_case_1(read_filepath, write_filepath, frequency, temporary_save):
    """Reads data for case 1

    Args:
        read_filepath (str): Existing loocation of the data file
        write_filepath (str): Location to save the new file
        frequency (str): The selected frequency.
                    Note: Due to size issues, for case 1 only supports W and M
        temporary_save (bool, Optional): If true it saves the dataframe on chunks
                                         Deals with memory breaks.
    """
    # Initialize parameters to ensure stable loading

    chunksize = 10**6
    dict_dtypes = {
        "CENTRALE": "category",
        "FILIAAL": "category",
        "ALDIARTNR": "category",
        "ST": np.float32,
        "VRD": np.float16,
    }

    # Initialize the reading itterator
    tp = pd.read_csv(
        read_filepath,
        iterator=True,
        chunksize=chunksize,
        sep=";",
        dtype=dict_dtypes,
        parse_dates=["DATUM"],
        infer_datetime_format=True,
        decimal=",",
    )

    # Drop stock column for now
    df = pd.concat(tp, ignore_index=True).drop("VRD", axis=1)

    # Name the columns
    cols = ["DC", "Shop", "Item", "date", "y"]
    df.columns = cols

    # Delete the itterator to release some memory
    del tp
    gc.collect()
    # Main loading idea!
    # Process the df in chunks: -> At each chunk sample to the given frequency
    # Then concat!

    # Initialize chunk size based on the frequency
    if frequency == "W":
        chunk_size = 14
    elif frequency == "M":
        chunk_size = 59
    else:
        raise ValueError(
            "Currently supporting only Weekly(W) and Monthly(M) frequencies for case 1"
        )
    # Initialize values for the chunks
    start_date = df["date"].min()
    chunk_period = datetime.timedelta(days=chunk_size)
    temp_date = start_date + chunk_period

    # Initialize the df on the first chunk!
    out_df = df[(df["date"] < temp_date) & (df["date"] > start_date)]
    start_date = temp_date - datetime.timedelta(days=1)

    # Initialize the names on the unique_id
    # Lower level is the product-level
    out_df = out_df.drop(["DC", "Shop"], axis=1)
    out_df = out_df.rename(columns={"Item": "unique_id"})
    # Pivot and resample to the given frequency
    out_df = (
        pd.pivot_table(
            out_df, index="unique_id", columns="date", values="y", aggfunc="sum"
        )
        .resample(frequency, axis=1)
        .sum()
    )
    # Itterate over the other chunks:
    while start_date + chunk_period < df["date"].max():
        # Update the date
        temp_date = start_date + chunk_period

        # Filter on the given period
        temp_df = df[(df["date"] < temp_date) & (df["date"] > start_date)]
        start_date = temp_date - datetime.timedelta(days=1)

        # Update names on the unique_id, drop columns, pivot & resample
        temp_df = temp_df.drop(["DC", "Shop"], axis=1)
        temp_df = temp_df.rename(columns={"Item": "unique_id"})

        temp_df = (
            pd.pivot_table(
                temp_df, index="unique_id", columns="date", values="y", aggfunc="sum"
            )
            .resample(frequency, axis=1)
            .sum()
        )

        # Add to the main df
        out_df = pd.concat([out_df, temp_df], axis=1)

        # Save at each itteration to deal with memory breaks
        if temporary_save:
            out_df.to_csv(write_filepath)
    # Final save
    # out_df = fix_duplicate_cols(out_df)
    return out_df


def read_case_2(read_filepath):
    """Reads data for case 2

    Args:
        read_filepath (str): Existing loocation of the data file
    """

    # Read data from an excel format
    xl = pd.ExcelFile(read_filepath)
    df = pd.read_excel(
        xl, "data"
    )  # data is the name of the tab with the time series data

    # Rename columns
    df = df.rename(
        columns={
            "Verkoopdoc": "OrderNum",
            "klantnr.": "CostumerNum",
            "artikelnr.": "ID",
            "orderhoeveelheid VE": "y",
            "Gecr. op": "date",
            "GewLevrDat": "DeliveryDate",
            "land": "Country",
            "productfamilie": "ProductFamily",
            "internalgroup": "Internal",
            "segment": "Segment",
        }
    )

    # Change some data types
    items = df["ID"].values
    # Splitting the string,
    # Getting the 2nd value after the split and converting to a number
    items_num = [int(single_item.split(" ")[1]) for single_item in items]
    df["ID"] = items_num
    # Replace delimiters
    df["y"] = [
        float(val.replace(",", "."))
        if type(val) == str
        else float(str(val).replace(",", "."))
        for val in df["y"].values
    ]
    # Convert to datetime
    df["date"] = [pd.Timestamp(date, freq="D") for date in df["date"].values]

    # prepare the unique_id col
    # Format: Product Family + ID
    df["unique_id"] = [
        "-".join([product, str(id)])
        for product, id in zip(df["ProductFamily"], df["ID"])
    ]

    # keeping only specific columns
    cols_to_keep = ["date", "y", "unique_id"]
    df = df[cols_to_keep]

    return df


def read_case_3(
    read_filepath,
):
    """Reads data for case 4

    Args:
        read_filepath (str): Existing loocation of the data file
    """

    # Loading
    df = pd.read_csv(read_filepath)

    # Removing instances with bad status
    ids = df[(df["Status"] == 4) | (df["Status"].isna()) | (df["Exclincl"] != 1)].index
    df = df.drop(ids)

    # Convert date to datetime
    df["Datum"] = pd.to_datetime(df["Datum"])

    # keep only sales
    df = df[df["Trans"] == "VK"]
    df["Inuit"] = df["Inuit"].astype(float)

    # Group
    df = df.groupby(["Groep", "Resource", "Datum"]).agg({"Inuit": "sum"}).reset_index()

    # Convert to positive
    df["Inuit"] = df["Inuit"] * -1

    # Merge on the names to make the unique_id
    # format: Shop - group
    df["unique_id"] = [
        str(shop) + "-" + str(group) for shop, group in zip(df["Resource"], df["Groep"])
    ]

    # Drop cols
    df = df.drop(["Groep", "Resource"], axis=1)

    # Change column names
    cols = ["date", "y", "unique_id"]
    df.columns = cols

    return df


def read_case_4(read_filepath):
    """Reads data for case 5

    Args:
        read_filepath (str): Existing loocation of the data file
    """
    # Loading
    df = pd.read_excel(read_filepath, skiprows=9)

    # Drop two columns
    df = df.drop(["Unnamed: 0", "Unnamed: 2"], axis=1)

    # We focus on sales
    df = df[df["Status"] == "Gewonnen"]

    # Editting the items names
    # Convert to str and titlecase
    df.loc[:, "Modellen van interesse"] = (
        df["Modellen van interesse"].astype(str).str.title()
    )
    df["Merk"] = df["Merk"].astype(str).str.title()

    # Keep only the last item shown in case it is of the right brand
    df.loc[:, "Modellen van interesse"] = [
        [i for i in a.split(",") if str(b) in i]
        for a, b in zip(df["Modellen van interesse"], df["Merk"])
    ]
    df.loc[:, "Keep"] = [len(a) for a in df["Modellen van interesse"].values]
    df = df[df["Keep"] > 0]
    df["Modellen van interesse"] = [
        item[0] for item in df["Modellen van interesse"].values
    ]

    # Remove brands without naming
    df.loc[:, "Keep"] = [len(a.split(" ")) for a in df["Modellen van interesse"].values]
    df = df[df["Keep"] > 1]

    # Fix issues with some items
    df.loc[:, "Modellen van interesse"] = [
        " ".join(a.split(" ")[1:]) if a.split(" ")[1] == "Audi" else a
        for a in df["Modellen van interesse"].values
    ]

    # fix the issue with RS 6 and RS6, merge characters if a number is after a letter
    df.loc[:, "Modellen van interesse"] = [
        " ".join(
            [
                "".join([a.split(" ")[i], a.split(" ")[i + 1]])
                if a.split(" ")[i + 1].isdigit()
                else a.split(" ")[i]
                for i in range(len(a.split(" ")) - 1)
            ]
            + [a.split(" ")[-1]]
        )
        for a in df["Modellen van interesse"].values
    ]

    # Manualy replace some values for a car
    df.loc[:, "Modellen van interesse"] = df.loc[
        :, "Modellen van interesse"
    ].str.replace("!", " ")
    df.loc[:, "Modellen van interesse"] = df.loc[
        :, "Modellen van interesse"
    ].str.replace("Multivan77", "Multivan")
    df.loc[:, "Modellen van interesse"] = df.loc[
        :, "Modellen van interesse"
    ].str.replace("Multivan7", "Multivan")

    # keep onl standard models not extras
    df.loc[:, "Modellen van interesse"] = [
        " ".join(a.split(" ")[:2]) for a in df["Modellen van interesse"].values
    ]

    # Add the sale
    df.loc[:, "Sale"] = 1

    # Edit dates
    df.loc[:, "Aanmaakdatum"] = pd.to_datetime(df["Aanmaakdatum"], format="%d/%m/%Y")

    # Pick a specific start date
    start_date = datetime.datetime.strptime("01-12-2016", "%d-%m-%Y")
    df = df[df["Aanmaakdatum"] > start_date]

    # Keep only relevant columns
    cols = ["Aanmaakdatum", "Modellen van interesse", "Sale"]
    renamed_cols = ["date", "unique_id", "y"]
    df = df[cols]
    df.columns = renamed_cols

    # Aggregate
    df = df.groupby(["date", "unique_id"]).sum().reset_index()

    return df
