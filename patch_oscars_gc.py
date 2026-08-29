import re

with open("oscars/src/collectors/mark_sweep_branded/gc_box.rs", "r") as f:
    content = f.read()

# Add root_count to GcBox
target_gcbox = """    pub(crate) type_id: TypeId,
    /// The user value.
    pub(crate) value: T,
}"""
replacement_gcbox = """    pub(crate) type_id: TypeId,
    pub(crate) root_count: Cell<usize>,
    /// The user value.
    pub(crate) value: T,
}"""
content = content.replace(target_gcbox, replacement_gcbox)

target_new = """            alloc_id,
            type_id: typeid::of::<T>(),
            value,
        }"""
replacement_new = """            alloc_id,
            type_id: typeid::of::<T>(),
            root_count: Cell::new(1),
            value,
        }"""
content = content.replace(target_new, replacement_new)

with open("oscars/src/collectors/mark_sweep_branded/gc_box.rs", "w") as f:
    f.write(content)

with open("oscars/src/collectors/mark_sweep_branded/gc.rs", "r") as f:
    content = f.read()

# Remove Copy and change Clone, add Drop
target_copy = """impl<'gc, T: Trace + ?Sized + 'gc> Copy for Gc<'gc, T> {}
impl<'gc, T: Trace + ?Sized + 'gc> Clone for Gc<'gc, T> {
    fn clone(&self) -> Self {
        *self
    }
}"""
replacement_copy = """impl<'gc, T: Trace + ?Sized + 'gc> Clone for Gc<'gc, T> {
    fn clone(&self) -> Self {
        let count = unsafe { &(*self.ptr.as_ptr().as_ptr()).0.root_count };
        count.set(count.get() + 1);
        Self {
            ptr: self.ptr,
            _marker: core::marker::PhantomData,
        }
    }
}

impl<'gc, T: Trace + ?Sized + 'gc> Drop for Gc<'gc, T> {
    fn drop(&mut self) {
        // SAFETY: The allocator does not unmap memory, so the block is still valid memory.
        // Even if the object was collected and the block re-used, the `root_count` will just be corrupted.
        // Wait, if it was collected, it means root_count WAS 0! So it won't be collected if we still have a Gc pointing to it!
        // Because the Collector checks root_count during collection!
        let count = unsafe { &(*self.ptr.as_ptr().as_ptr()).0.root_count };
        if count.get() > 0 {
            count.set(count.get() - 1);
        }
    }
}"""
content = content.replace(target_copy, replacement_copy)

with open("oscars/src/collectors/mark_sweep_branded/gc.rs", "w") as f:
    f.write(content)
print("Patched Gc and GcBox")
