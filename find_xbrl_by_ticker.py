import urllib2, re, os, urllib, csv
import xml.etree.ElementTree as ET

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
		print 'downloading %s' % url
		response = urllib2.urlopen(url)
		content = response.read()
		if not os.path.exists(CACHES_DIR):
			os.makedirs(CACHES_DIR)
		with open(cached_content, 'w') as f:
			f.write(content)
		return cached_content


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
	

def find_filings_with_xbrl_ref(ticker):
	filings_url = 'http://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=%s&count=100&type=10-k&output=xml' % ticker
	filings_xml = _download_url(filings_url)
	root = ET.fromstring(filings_xml)
	results = []
	for el in root.findall('./results/filing'):
		if el.find('XBRLREF') is not None:
			results.append({
				'date': el.find('dateFiled').text,
				'url': el.find('filingHREF').text
			})
	return results


def find_xbrl_url_in_filing_by_url(url, ticker):
	filing = _download_url(url)
	pattern = '/Archives/edgar/data/\w+/\w+/%s-\d+\.xml' % ticker.lower()
	m = re.search(pattern, filing, re.DOTALL | re.UNICODE)
	if m:
		return 'http://www.sec.gov%s' % m.group(0)
	else:
		return None


def _find_element_value(xml, ns, name, year, xbrl_url):
	elements = xml.findall('{%s}%s' % (ns['us-gaap'], name), ns)
	if len(elements) == 0:
		return None

	contexts = []

	for e in elements:
		contexts.append((e.get('contextRef'), e.text))

	# Leave only records for the last year: year of publication or the previous one
	# print '1', contexts
	filtered = filter(lambda c: year in c[0], contexts)
	if len(filtered) == 0:
		filtered = filter(lambda c: str(int(year) - 1) in c[0], contexts)
	# print '2', filtered

	# Always ignore records with '_us-gaap_' in name
	filtered = filter(lambda c: '_us-gaap_' not in c[0], filtered)
	if len(filtered) == 0:
		return None
	# print '3', filtered

	# Then remove long records that are prolongation of the first short one,
	# e.g. 'I2012Q4_us-gaap_StatementScenarioAxis...' following simple 'I2012Q4'
	if (len(filtered) > 1):
		filtered = sorted(filtered, lambda c1, c2: len(c1[0]) - len(c2[0]))
		filtered = filter(lambda c: re.match('^%s.+$' % filtered[0][0], c[0], re.DOTALL) is None, filtered)
		# print '4', filtered

	if (len(filtered) > 1 or len(filtered) == 0):
		raise Exception('Could not choose correct %s for %s in %s: %s' % (name, year, xbrl_url, filtered))

	# print 'Chose context %s for %s in %s at %s' % (filtered[0][0], name, year, xbrl_url)
	value = filtered[0][1]

	return value


def get_xbrl_data(xbrl_url, date):
	xml_file = _download_url_to_file(xbrl_url)
	xml, ns = _parse_xml_with_ns(xml_file)

	# print 'processing %s' % xbrl_url

	year = date[:4]

	result = {}

	for name in XBRL_ELEMENTS:
		value = _find_element_value(xml, ns, name, year, xbrl_url)
		if value is not None:
			result[name] = value
	return result


def find_xbrls(ticker):
	filings = find_filings_with_xbrl_ref(ticker)
	result = {}
	for f in filings:
		print 'processing %s as of %s' % (ticker, f['date'])
		xbrl_url = find_xbrl_url_in_filing_by_url(f['url'], ticker)
		xbrl_data = get_xbrl_data(xbrl_url, f['date'])

		result[f['date']] = xbrl_data

	return result

if __name__ == '__main__':
	tickers = [
		'KO',
		'DELL',
		'MSFT',
		'GOOG',
		'MMM'
	]
	output_csv = 'company_results_over_years.txt'

	with open(output_csv, 'wb') as csvfile:
		writer = csv.writer(csvfile, dialect='excel')

		writer.writerow(['Company', 'Date'] + XBRL_ELEMENTS)

		for ticker in tickers:
			xbrls = find_xbrls(ticker)
			# import pprint
			# pp = pprint.PrettyPrinter(indent = 4)
			# pp.pprint(xbrls)
			for date in xbrls:
				xbrl = xbrls[date]
				row = [ticker, date]
				for element in XBRL_ELEMENTS:
					row.append(xbrl.get(element))
				writer.writerow(row)

