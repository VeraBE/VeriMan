bins = {
	'verisol_path': '/home/user/verisol',
	'corral_path': '/home/user/verisol/corral/bin/Debug',
	'solc_path': '/home/user/solc_0_4_25' # Needs a version lower than 0.5
}

contract = {
	'name': '',  # If '' then the file name will be used
	'path': '/home/user/contracts/InOrderHard.sol',
	'args': (),
	'condition': 'num_calls > 1',  # Solidity, added only if condition_line > 0 or fully_verify_condition
	'state': 'b_called',  # Solidity, optional
	'fully_verify_condition': True,
	'condition_line': 0
}

bounds = {
	'loops': 100,  # Affects Corral, and Manticore execution only if loop_delimiter
	'txs': 5,
	'procs': 3,  # Some errors didn't show up when using multiple procs
	'user_initial_balance': 100,
	'avoid_constant_txs': False,  # Avoid all TXs that have no effect on the storage
	'loop_delimiter': False
}

output = {
	'report_invalid': False,
	'verbose': False,
	'cleanup': True
}