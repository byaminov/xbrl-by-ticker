# Introduction

This Python tool helps you download XBRL data for companies by their ticker codes from http://www.sec.gov/ website. I used it to generate data for financial analysis.

This particular tool does following:
* downloads year end 10-K XBRL reports per company ticker
* includes all available years
* extracts a number of GAAP fields from XBRL document, corresponding to the year end report
* put everything in a resulting CSV file for further usage in statistics tools.

# Usage

Run following command using [Python](https://www.python.org/):

	python find_xbrl_by_ticker.py <file with tickers> [<output CSV filename>]

The first parameter in a file with company tickers to download. One ticker per line. The second parameter gives the file where to print the results. If the file is not given, then results are printed into standard output.

The rest of configuration like which report to download and which GAAP properties to extract is hardcoded in the `find_xbrl_by_ticker.py` script. So if you need other data - you can modify it there.

The script tries to find the GAAP elements corresponding to the year end in the XBRL report. Because the format of XML file is not very strict, the script uses some heuristics to determine which element is the right one.
