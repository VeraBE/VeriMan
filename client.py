from veriman import VeriMan

# TODO improve efficiency:

if __name__ == '__main__':
    veriman = VeriMan()
    config = VeriMan.parse_config('config.json')
    original_predicates = config.instrumentation.predicates

    if config.verification.verisol.use and config.instrumentation.instrument and len(config.instrumentation.predicates) > 1:
        for index, predicate in enumerate(original_predicates):
            print('[-] Checking predicate no.', index + 1)
            config.instrumentation.predicates = [predicate]
            proof_found, verisol_counterexample = veriman.analyze_contract(config)
            print('')
    else:
        proof_found, verisol_counterexample = veriman.analyze_contract(config)