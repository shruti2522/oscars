import re

with open("oscars/src/collectors/mark_sweep_branded/gc_box.rs", "r") as f:
    content = f.read()

# Add root_count and finalize_fn to GcBox
target_gcbox = """    pub(crate) color: Cell<GcColor>,
    /// Type-erased trace function.
    pub(crate) trace_fn: TraceFn,
    /// Type-erased finalize and free fn
    pub(crate) drop_fn: DropFn,"""
replacement_gcbox = """    pub(crate) color: Cell<GcColor>,
    /// Type-erased trace function.
    pub(crate) trace_fn: TraceFn,
    pub(crate) finalize_fn: unsafe fn(NonNull<u8>),
    pub(crate) root_count: Cell<usize>,
    /// Type-erased finalize and free fn
    pub(crate) drop_fn: DropFn,"""
content = content.replace(target_gcbox, replacement_gcbox)

target_new = """    pub(crate) fn new(value: T, trace_fn: TraceFn, drop_fn: DropFn, alloc_id: usize) -> Self {
        Self {
            color: Cell::new(GcColor::White),
            trace_fn,
            drop_fn,
            alloc_id,"""
replacement_new = """    pub(crate) fn new(value: T, trace_fn: TraceFn, drop_fn: DropFn, alloc_id: usize) -> Self {
        unsafe fn finalize_node<T: Trace>(ptr: NonNull<u8>) {
            let item_ptr = ptr.cast::<PoolItem<GcBox<T>>>();
            unsafe {
                (*item_ptr.as_ptr()).0.value.run_finalizer();
            }
        }
        Self {
            color: Cell::new(GcColor::White),
            trace_fn,
            finalize_fn: finalize_node::<T>,
            root_count: Cell::new(1),
            drop_fn,
            alloc_id,"""
content = content.replace(target_new, replacement_new)

with open("oscars/src/collectors/mark_sweep_branded/gc_box.rs", "w") as f:
    f.write(content)

with open("oscars/src/collectors/mark_sweep_branded/gc.rs", "r") as f:
    content = f.read()

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
        let count = unsafe { &(*self.ptr.as_ptr().as_ptr()).0.root_count };
        if count.get() > 0 {
            count.set(count.get() - 1);
        }
    }
}"""
content = content.replace(target_copy, replacement_copy)

with open("oscars/src/collectors/mark_sweep_branded/gc.rs", "w") as f:
    f.write(content)

with open("oscars/src/collectors/mark_sweep_branded/mod.rs", "r") as f:
    content = f.read()

# Update drop_node to NOT call finalizer
target_drop = """pub(crate) unsafe fn drop_node<T: Trace>(
    pool: &mut PoolAllocator<'static>,
    ptr: core::ptr::NonNull<u8>,
) {
    let item_ptr = ptr.cast::<PoolItem<GcBox<T>>>();
    unsafe {
        // Run finalizer
        (*item_ptr.as_ptr()).0.value.run_finalizer();
        // Free item
        pool.free(item_ptr);
    }
}"""
replacement_drop = """pub(crate) unsafe fn drop_node<T: Trace>(
    pool: &mut PoolAllocator<'static>,
    ptr: core::ptr::NonNull<u8>,
) {
    let item_ptr = ptr.cast::<PoolItem<GcBox<T>>>();
    unsafe {
        // Free item
        pool.free(item_ptr);
    }
}"""
content = content.replace(target_drop, replacement_drop)

# Update sweep to run finalizers first, and trace root_count
target_sweep = """        let mut tracer = Tracer::new();

        trace_external(&mut tracer);

        for link_ptr in self.sentinel.iter() {"""
replacement_sweep = """        let mut tracer = Tracer::new();

        trace_external(&mut tracer);

        for ptr in self.pool.borrow().iter_live_slots() {
            unsafe {
                let gc_box = &(*ptr.cast::<crate::alloc::mempool3::PoolItem<GcBox<()>>>().as_ptr()).0;
                if gc_box.root_count.get() > 0 {
                    (gc_box.trace_fn)(ptr, &mut tracer);
                }
            }
        }

        for link_ptr in self.sentinel.iter() {"""
content = content.replace(target_sweep, replacement_sweep)

target_dead = """        // Phase 3: sweep all slots. Collect unmarked ones, then invalidate and free them.
        use crate::alloc::mempool3::PoolItem;
        let dead: Vec<(NonNull<u8>, DropFn)> = {
            let pool = self.pool.borrow();
            pool.iter_live_slots()
                .filter_map(|ptr| unsafe {
                    let gc_box = &(*ptr.cast::<PoolItem<GcBox<()>>>().as_ptr()).0;
                    if gc_box.color.get() == GcColor::Black {
                        gc_box.color.set(GcColor::White);
                        None
                    } else {
                        Some((ptr, gc_box.drop_fn))
                    }
                })
                .collect()
        };
        {
            let mut pool = self.pool.borrow_mut();
            for (ptr, drop_fn) in dead {
                unsafe {
                    (*ptr.cast::<PoolItem<GcBox<()>>>().as_ptr()).0.alloc_id =
                        GcBox::<()>::FREED_ALLOC_ID;
                    (drop_fn)(&mut pool, ptr);
                }
            }
        }"""
replacement_dead = """        // Phase 3: sweep all slots. Collect unmarked ones, then invalidate and free them.
        use crate::alloc::mempool3::PoolItem;
        let dead: Vec<(NonNull<u8>, DropFn, unsafe fn(NonNull<u8>))> = {
            let pool = self.pool.borrow();
            pool.iter_live_slots()
                .filter_map(|ptr| unsafe {
                    let gc_box = &(*ptr.cast::<PoolItem<GcBox<()>>>().as_ptr()).0;
                    if gc_box.color.get() == GcColor::Black {
                        gc_box.color.set(GcColor::White);
                        None
                    } else {
                        Some((ptr, gc_box.drop_fn, gc_box.finalize_fn))
                    }
                })
                .collect()
        };
        
        for (ptr, _, finalize_fn) in &dead {
            unsafe {
                (finalize_fn)(*ptr);
            }
        }
        
        {
            let mut pool = self.pool.borrow_mut();
            for (ptr, drop_fn, _) in dead {
                unsafe {
                    (*ptr.cast::<PoolItem<GcBox<()>>>().as_ptr()).0.alloc_id =
                        GcBox::<()>::FREED_ALLOC_ID;
                    (drop_fn)(&mut pool, ptr);
                }
            }
        }"""
content = content.replace(target_dead, replacement_dead)

# Update Collector::drop
target_drop_coll = """        // Then iterate through pool and call drop_fn for all allocated items
        for item in self.pool.borrow_mut().iter() {
            unsafe {
                let node = item.cast::<PoolItem<GcBox<()>>>();
                let drop_fn = (*node.as_ptr()).0.drop_fn;
                (*node.as_ptr()).0.alloc_id = GcBox::<()>::FREED_ALLOC_ID;
                (drop_fn)(&mut self.pool.borrow_mut(), item);
            }
        }"""
replacement_drop_coll = """        // Then iterate through pool and call drop_fn for all allocated items
        // Wait, we need to run finalizers first here too!
        let dead: Vec<(NonNull<u8>, DropFn, unsafe fn(NonNull<u8>))> = self.pool.borrow_mut().iter().map(|item| unsafe {
            let node = item.cast::<PoolItem<GcBox<()>>>();
            let drop_fn = (*node.as_ptr()).0.drop_fn;
            let finalize_fn = (*node.as_ptr()).0.finalize_fn;
            (item, drop_fn, finalize_fn)
        }).collect();
        for (item, _, finalize_fn) in &dead {
            unsafe {
                (finalize_fn)(*item);
            }
        }
        for (item, drop_fn, _) in dead {
            unsafe {
                let node = item.cast::<PoolItem<GcBox<()>>>();
                (*node.as_ptr()).0.alloc_id = GcBox::<()>::FREED_ALLOC_ID;
                (drop_fn)(&mut self.pool.borrow_mut(), item);
            }
        }"""
content = content.replace(target_drop_coll, replacement_drop_coll)

with open("oscars/src/collectors/mark_sweep_branded/mod.rs", "w") as f:
    f.write(content)

print("Patched oscars full!")
