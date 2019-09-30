from veriman import VeriMan

if __name__ == '__main__':
    veriman = VeriMan()

    config = VeriMan.parse_config('config.json')

    if config.verification.verisol.use and config.instrumentation.instrument:
        original_predicates = config.instrumentation.predicates

        for predicate in original_predicates:
            config.instrumentation.predicates = [predicate]
            proof_found, verisol_counterexample = veriman.analyze_contract(config)
    else:
        proof_found, verisol_counterexample = veriman.analyze_contract(config)