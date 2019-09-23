import commentjson
from types import SimpleNamespace as Namespace

def read_config(file_name):
	with open(file_name) as config_file:
		config_file_string = config_file.read()
		return commentjson.loads(config_file_string, object_hook=lambda d: Namespace(**d))