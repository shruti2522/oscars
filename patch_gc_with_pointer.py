import sys

# 1. gc_box.rs: set initial root_count to 0
with open("oscars/src/collectors/mark_sweep_branded/gc_box.rs", "r") as f:
    content = f.read()

content = content.replace("root_count: Cell::new(1),", "root_count: Cell::new(0),")
with open("oscars/src/collectors/mark_sweep_branded/gc_box.rs", "w") as f:
    f.write(content)


# 2. gc.rs: make with_pointer increment root_count
with open("oscars/src/collectors/mark_sweep_branded/gc.rs", "r") as f:
    content = f.read()

target = """    pub(crate) fn with_pointer(ptr: PoolPointer<'static, GcBox<T>>) -> Self {
        Self {
            ptr,
            _marker: PhantomData,
        }
    }"""
replacement = """    pub(crate) fn with_pointer(ptr: PoolPointer<'static, GcBox<T>>) -> Self {
        let gc = Self {
            ptr,
            _marker: PhantomData,
        };
        let count = unsafe { &(*gc.ptr.as_ptr().as_ptr()).0.root_count };
        count.set(count.get() + 1);
        gc
    }"""
content = content.replace(target, replacement)
with open("oscars/src/collectors/mark_sweep_branded/gc.rs", "w") as f:
    f.write(content)

# 3. Revert the manual root_count increment in weak.rs that I added earlier
with open("oscars/src/collectors/mark_sweep_branded/weak.rs", "r") as f:
    content = f.read()

target_weak = """                let gc = crate::collectors::mark_sweep_branded::Gc::with_pointer(self.ptr);
                let count = &(*gc.ptr.as_ptr().as_ptr()).0.root_count;
                count.set(count.get() + 1);
                Some(gc)"""
replacement_weak = """                Some(crate::collectors::mark_sweep_branded::Gc::with_pointer(self.ptr))"""
content = content.replace(target_weak, replacement_weak)
with open("oscars/src/collectors/mark_sweep_branded/weak.rs", "w") as f:
    f.write(content)

print("Patched with_pointer to always increment root_count!")
