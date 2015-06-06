import urllib2, re, os, urllib
import xml.etree.ElementTree as ET

CACHES_DIR = '%s/download-cache' % os.path.dirname(os.path.abspath(__file__))

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


def get_xbrl_data(xbrl_url):
	xml_file = _download_url_to_file(xbrl_url)
	xml, ns = _parse_xml_with_ns(xml_file)

	# print 'processing %s' % xbrl_url

	result = {}
	def find_element(name):
		for e in xml.findall('{%s}%s' % (ns['us-gaap'], name), ns):
			if name not in result:
				result[name] = {}
			result[name][e.get('contextRef')] = e.text

	find_element('OtherAssetsCurrent')
	find_element('OtherAssetsNoncurrent')
	find_element('OtherAssets')
	find_element('OtherLiabilities')
	find_element('OtherLiabilitiesCurrent')
	find_element('OtherLiabilitiesNoncurrent')
	find_element('Assets')

	return result


def find_xbrls(ticker):
	filings = find_filings_with_xbrl_ref(ticker)
	result = {}
	for f in filings:
		# print '[%s] %s' % (f['date'], f['url'])
		xbrl_url = find_xbrl_url_in_filing_by_url(f['url'], ticker)
		xbrl_data = get_xbrl_data(xbrl_url)

		result[f['date']] = xbrl_data

	return result

if __name__ == '__main__':
	tickers = [
		# 'KO',
		# 'DELL',
		# 'MSFT',
		'GOOG'
	]

	import pprint
	pp = pprint.PrettyPrinter(indent = 4)

	for ticker in tickers:
		xbrls = find_xbrls(ticker)
		pp.pprint(xbrls)
