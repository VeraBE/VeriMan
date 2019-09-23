from veriman import VeriMan
from tools import read_config

# TODO improve efficiency:

if __name__ == '__main__':
    veriman = VeriMan()
    config = read_config('config.json')
    original_predicates = config.instrumentation.predicates

    if config.verification.verify and config.instrumentation.instrument and len(config.instrumentation.predicates) > 0:
        for index, predicate in enumerate(original_predicates):
            print('[-] Checking predicate no.', index)
            config.instrumentation.predicates = [predicate]
            proof_found, verisol_counterexample = veriman.analyze_contract(config)
            print('')
    else:
        proof_found, verisol_counterexample = veriman.analyze_contract(config)