import urllib2, re, os, urllib, csv, sys, time
import xml.etree.ElementTree as ET
from datetime import datetime


CACHES_DIR = '%s/download-cache' % os.path.dirname(os.path.abspath(__file__))
XBRL_ELEMENTS = [
	'OtherAssetsCurrent', 
	'OtherAssetsNoncurrent', 
	'OtherAssets', 
	'OtherLiabilities', 
	'OtherLiabilitiesCurrent', 
	'OtherLiabilitiesNoncurrent', 
	'Assets'
]


def _download_url_to_file(url):
	cached_content = '%s/%s' % (CACHES_DIR, urllib.quote(url, ''))
	if os.path.exists(cached_content):
		return cached_content
	else:
		print 'downloading %s (%s)' % (url, datetime.now().time())

		max_tries = 3
		for try_count in range(max_tries + 1):
			try:
				response = urllib2.urlopen(url)
				content = response.read()
				if not os.path.exists(CACHES_DIR):
					os.makedirs(CACHES_DIR)
				with open(cached_content, 'w') as f:
					f.write(content)
				return cached_content
			except Exception as e:
				if try_count >= max_tries:
					raise
				else:
					# Wait for a while
					time.sleep(5)
					print 'retrying %s after error: %s' % (url, e)


def _download_url(url):
	cached_content = _download_url_to_file(url)
	with open(cached_content, 'r') as f:
		return f.read()


def _parse_xml_with_ns(xml_file):
	events = "start", "start-ns"
	root = None
	ns_map = []
	for event, elem in ET.iterparse(xml_file, events):
		# print 'handling %s on %s' % (event, elem)
		if event == "start-ns":
			ns_map.append(elem)
		elif event == "start":
			if root is None:
				root = elem
	
	return ET.ElementTree(root), dict(ns_map)


def find_company_xml(ticker):
	filings_url = 'http://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=%s&count=100&type=10-k&output=xml' % ticker
	filings_xml = _download_url(filings_url)
	if 'No matching Ticker Symbol' in filings_xml:
		return None
	return ET.fromstring(filings_xml)
	

def find_filings_with_xbrl_ref(company_xml):
	results = []
	for el in company_xml.findall('./results/filing'):
		if el.find('XBRLREF') is not None:
			results.append({
				'date': el.find('dateFiled').text,
				'url': el.find('filingHREF').text
			})
	return results


def find_xbrl_url_in_filing_by_url(url, ticker):
	filing = _download_url(url)
	pattern = '/Archives/edgar/data/\w+/\w+/[a-z]+-\d+\.xml'
	m = re.search(pattern, filing, re.DOTALL | re.UNICODE)
	if m:
		return 'http://www.sec.gov%s' % m.group(0)
	else:
		print 'Could not find XBRL XML URL by pattern [%s] in %s (company %s)' % (pattern, url, ticker)
		return None


def _find_element_value(xml, ns, name, period_end_date, xbrl_html_url):
	elements = xml.findall('{%s}%s' % (ns['us-gaap'], name), ns)
	if len(elements) == 0:
		return None

	contexts = []

	for e in elements:
		contexts.append((e.get('contextRef'), e.text))

	
	# Always ignore records with '_us-gaap_' in name
	filtered = filter(lambda c: '_us-gaap' not in c[0], contexts)
	if len(filtered) == 0:
		return None


	# Filter only contexts related to the document end date.
	# There are different date formats used in different XBRLs.
	date_of_interest = datetime.strptime(period_end_date, '%Y-%m-%d')
	expected_date_formats = [
		'%Y%m%d',
		'%m_%d_%Y',
		'%-m_%d_%Y',
		'%d%b%Y',
		'%-d%b%Y',
		'%Y',
	]
	for format in expected_date_formats:
		date_string = date_of_interest.strftime(format)
		filtered_by_date = filter(lambda c: date_string in c[0], filtered)
		if len(filtered_by_date) > 0:
			used_date_format = date_string
			break
	if len(filtered_by_date) == 0:
		# If length is the same, pick the last alphabetically, e.g. ['c00030', 'c00006'] -> 'c00030'
		if len(filtered) > 1 and len(filter(lambda c: len(c[0]) != len(filtered[0][0]), filtered)) == 0:
			print 'choosing %s from %s' % ([ sorted(filtered, key = lambda c: c[0], reverse = True)[0] ], filtered)
			filtered = [ sorted(filtered, key = lambda c: c[0], reverse = True)[0] ]
		else:
			raise Exception(('Could not choose correct %s for %s in %s : it uses neither of ' +
				'expected date formats. Original contexts: %s') % \
				(name, period_end_date, xbrl_html_url, contexts))
	else:
		filtered = filtered_by_date


	# Then remove long records that are prolongation of the first short one,
	# e.g. 'I2012Q4_us-gaap_StatementScenarioAxis...' following simple 'I2012Q4'
	if len(filtered) > 1:
		filtered = sorted(filtered, lambda c1, c2: len(c1[0]) - len(c2[0]))
		filtered = filter(lambda c: re.match('^%s.+$' % filtered[0][0], c[0], re.DOTALL) is None, filtered)

	# Or try to remove those which are aaa20100610_BlaBlaBla
	if len(filtered) > 1:
		filtered = sorted(filtered, lambda c1, c2: len(c1[0]) - len(c2[0]))
		filtered = filter(lambda c: re.match('^.{,10}%s.{15,}$' % used_date_format, c[0], re.DOTALL) is None, filtered)



	if len(filtered) > 1 or len(filtered) == 0:
		message = 'Could not choose correct %s for %s in %s : %s. Original contexts: %s' % \
			(name, period_end_date, xbrl_html_url, filtered, contexts)
		if len(filtered) > 1:
			raise Exception(message)
		else:
			print message
			return None

	# print 'Chose context %s for %s in %s at %s' % (filtered[0][0], name, period_end_date, xbrl_html_url)
	value = filtered[0][1]

	return value


def get_xbrl_data(xbrl_xml_url, xbrl_html_url):
	xml_file = _download_url_to_file(xbrl_xml_url)
	xml, ns = _parse_xml_with_ns(xml_file)

	# print 'processing %s' % xbrl_xml_url

	period_focus_element = xml.find('{%s}DocumentFiscalPeriodFocus' % ns['dei'], ns)
	period_focus = period_focus_element.text if period_focus_element is not None else None
	if period_focus is not None and period_focus != 'FY':
		# print 'ignoring report not focusing on full year: %s (%s)' % (period_focus, xbrl_xml_url)
		return None

	period_end_date = xml.find('{%s}DocumentPeriodEndDate' % ns['dei'], ns).text

	result = { 'DocumentPeriodEndDate': period_end_date }

	for name in XBRL_ELEMENTS:
		result[name] = _find_element_value(xml, ns, name, period_end_date, xbrl_html_url)

	return result


def find_xbrls(company_xml):
	filings = find_filings_with_xbrl_ref(company_xml)
	xbrls = []
	for f in filings:
		print 'processing 10-K of %s published on %s' % (ticker, f['date'])
		xbrl_url = find_xbrl_url_in_filing_by_url(f['url'], ticker)
		xbrl_data = get_xbrl_data(xbrl_url, f['url'])
		if xbrl_data is not None:
			xbrls.append(xbrl_data)

	return xbrls

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print 'Usage: python find_xbrl_by_ticker.py <file with tickers (one per line)> [<output CSV filename>]'
		sys.exit(0)

	with open(sys.argv[1], 'r') as f:
		tickers = map(lambda t: t.replace('\n', '').replace('\r', ''), f.readlines())

	if len(sys.argv) > 2:
		output_csv = sys.argv[2]
	else:
		output_csv = 'company_results_over_years.txt'

	print 'Fetching XBRLs into file %s for %s companies: %s...' % (output_csv, len(tickers), 
		str(tickers[0:3]).replace('[', '').replace(']', ''))

	with open(output_csv, 'wb') as csvfile:
		writer = csv.writer(csvfile, dialect='excel')

		writer.writerow(['Ticker', 'CIK', 'Company name', 'DocumentPeriodEndDate'] + XBRL_ELEMENTS)

		for ticker in tickers:
			try:
				company_xml = find_company_xml(ticker)
				if company_xml is None:
					print 'NO company found at http://www.sec.gov/ by ticker %s' % ticker
					continue

				cik = int(company_xml.find('./companyInfo/CIK').text)
				company_name = company_xml.find('./companyInfo/name').text

				xbrls = find_xbrls(company_xml)

				for xbrl in xbrls:
					row = [ticker, cik, company_name, xbrl.get('DocumentPeriodEndDate')]
					for element in XBRL_ELEMENTS:
						row.append(xbrl.get(element))
					writer.writerow(row)

			except Exception as e:
				raise
				# print 'Failed to process %s: %s' % (ticker, e)

	print 'Summary of XBRL reports is ready in CSV file %s' % output_csv