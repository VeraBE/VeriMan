bins = {
	'verisol_path': '/home/user/verisol',
	'corral_path': '/home/user/verisol/corral/bin/Debug',
	'solc_path': '/home/user/solc_0_4_25' # Needs a version lower than 0.5
}

contract = {
	'name': 'InOrdenParams',  # If '' then the file name will be used
	'path': '/home/user/contracts/InOrderParams.sol',
	'args': (),
	'line_number': 25,
	'line_condition': 'pc != 40'  # Added only if line_number > 0
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
	'verbose': False
}