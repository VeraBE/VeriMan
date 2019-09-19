bins = {
	'verisol_path': '/home/user/verisol/Binaries/VeriSol.dll' # Or your VeriSol command if you installed it globally
}

run = {
	'instrumentation': True,
	'predicates': [
		'previously(a_called) && a_called'
	], # Solidity's number and boolean operations + {->, previously, since, once, always}, added only if instrumentation
	'trace': True # VeriSol + Manticore
}

contract = {
	'name': '',  # If '' then the file name will be used
	'path': '/home/user/contracts/InOrderHard.sol', # For now it only supports contracts that work both on 0.5 and 0.4, because VeriSol needs 0.5 and Manticore 0.4
	'args': ()
}

bounds = {
	'loops': 10,  # Affects Manticore execution only if loop_delimiter
	'txs': 5,
	'procs': 3,  # Some errors didn't show up when using multiple procs
	'user_initial_balance': 100,
	'avoid_constant_txs': False,  # Avoid all TXs that have no effect on the storage
	'loop_delimiter': False,
	'user_accounts': 2, # FIXME get amount of accounts from VeriSol trace
	'fallback_data_size': 320
}

output = {
	'report_invalid': False,
	'verbose': True,
	'really_verbose': False,
	'cleanup': True
}