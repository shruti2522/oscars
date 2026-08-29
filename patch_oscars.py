import re

with open("oscars/src/collectors/mark_sweep_branded/mod.rs", "r") as f:
    content = f.read()

# Add collect_with_roots to MutationContext
target_mc_collect = """    pub fn collect(&self) {
        self.collector.collect();
    }"""
replacement_mc_collect = """    pub fn collect(&self) {
        self.collector.collect();
    }

    pub fn collect_with_roots<F>(&self, trace_external: F)
    where
        F: FnOnce(&mut Tracer),
    {
        self.collector.collect_with_roots(trace_external);
    }"""

if target_mc_collect in content:
    content = content.replace(target_mc_collect, replacement_mc_collect)
    with open("oscars/src/collectors/mark_sweep_branded/mod.rs", "w") as f:
        f.write(content)
    print("Patched MutationContext")
else:
    print("Could not find target_mc_collect")
