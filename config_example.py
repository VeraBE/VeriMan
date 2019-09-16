bins = {
	'verisol_path': '/home/user/verisol',
	'corral_path': '/home/user/verisol/corral/bin/Debug'
}

run = {
	'instrumentation': True,
	# FIXME sometimes the predicate should be included in more functions like: 'previously(!a_called) && a_called' and 'previously(!a_called) && b_called'
	'predicates': [
		'num_calls > 1'
	], # Solidity's number and boolean operations + {previously, since, once, always}, added only if instrumentation
	'trace': True # VeriSol + Manticore
}

contract = {
	'name': '',  # If '' then the file name will be used
	'path': '/home/user/contracts/InOrderHard.sol', # For now it only supports contracts that work both on 0.5 and 0.4, because VeriSol needs 0.5 and Manticore 0.4
	'args': ()
}

bounds = {
	'loops': 100,  # Affects Corral, and Manticore execution only if loop_delimiter
	'txs': 5,
	'procs': 3,  # Some errors didn't show up when using multiple procs
	'user_initial_balance': 100,
	'avoid_constant_txs': False,  # Avoid all TXs that have no effect on the storage
	'loop_delimiter': False,
	'user_accounts': 2,
	'fallback_data_size': 320
}

output = {
	'report_invalid': False,
	'verbose': False,
	'cleanup': True
}