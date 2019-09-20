contract = {
	'name': '', # If '' then the file name will be used
	'path': '/home/user/veriman/tests/InOrderHard.sol',
	'args': ()
}

output = {
	'report_invalid': False,
	'verbose': True,
	'really_verbose': False,
	'cleanup': True
}

instrumentation = {
	'instrument': True,
	'predicates': [
		'previously(a_called) && a_called'
	]
}

verification = {
	'verify': True,
	'verisol_path': '/home/user/verisol/Binaries/VeriSol.dll', # Or your VeriSol command if you installed it globally
	'txs': 5, # Max counterexample length
	# For Manticore:
	'loops': 10, # Affects only if loop_delimiter
	'procs': 3,  # For multithreading
	'user_initial_balance': 100,
	'avoid_constant_txs': False, # Avoid all TXs that have no effect on the storage
	'loop_delimiter': False,
	'user_accounts': 2,  # FIXME get amount of accounts from VeriSol trace
	'fallback_data_size': 320
}