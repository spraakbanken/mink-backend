# min-sb-backend

Flask application serving as a backend to Min Språkbank.


## Prerequisites
* [Python 3.6.1](http://python.org/) or newer
* [memcached](http://memcached.org/)


## Example calls with CURL

- Initialize Min Språkbank:
```
curl -X POST -u some_username 'localhost:9000/init'
```

- Upload a corpus:
```
curl -X PUT -u some_username -F "corpus_id=some_corpus_name" -F "files[0]=@/absolute/path/to/localfile1.txt" -F "files[1]=@/absolute/path/to/localfile2.txt" 'localhost:9000/upload-corpus'
```

- List corpora:
```
curl -u some_username 'localhost:9000/list-corpora'
```

- Upload config file:
```
curl -X PUT -u some_username -F "corpus_id=some_corpus_name" -F "files[0]=@/absolute/path/to/config.yaml;type=text/yaml" 'localhost:9000/upload-config'
```

- Remove corpus:
```
curl -X DELETE -u some_username 'localhost:9000/remove-corpus?corpus_id=some_corpus_name'
```

- Run Sparv:
```
curl -X PUT -u some_username -F "corpus_id=some_corpus_name" -F "exports=csv_export:csv,stats_export:freq_list,xml_export:pretty" 'localhost:9000/run-sparv'
```

- Check job status:
```
curl -X GET -u some_username -F "corpus_id=some_corpus_name" 'localhost:9000/check-status'
```

- List exports:
```
curl -X GET -u some_username -F "corpus_id=some_corpus_name" 'localhost:9000/list-exports'
```

- Download exports:
```
curl -X GET -u some_username -F "corpus_id=some_corpus_name" 'localhost:9000/download-exports'
```

- Update corpus:
```
curl -X PUT -u some_username -F "corpus_id=some_corpus_name" 'localhost:9000/update-corpus' -F "remove=some_filepath,another_filepath" -F "files[0]=@/absolute/path/to/some_localfile.txt"
```

- Clear annotations:
```
curl -X DELETE -u some_username -F "corpus_id=some_corpus_name" 'localhost:9000/clear-annotations'
```
