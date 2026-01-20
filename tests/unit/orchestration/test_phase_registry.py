"""
Unit tests for PhaseRegistry.
"""

import pytest
from src.orchestration.phase_registry import PhaseRegistry, PhaseDefinition


def test_phase_registry_initialization():
    """Test PhaseRegistry initialization."""
    registry = PhaseRegistry()
    assert len(registry) == 0
    assert registry.phases == {}


def test_register_phase():
    """Test phase registration."""
    registry = PhaseRegistry()
    
    def dummy_handler():
        return "result"
    
    phase = PhaseDefinition(
        name="test_phase",
        phase_number=1,
        dependencies=[],
        handler=dummy_handler,
        description="Test phase"
    )
    
    registry.register(phase)
    assert len(registry) == 1
    assert "test_phase" in registry
    assert registry.get_phase("test_phase") == phase


def test_get_execution_order_simple():
    """Test execution order for simple dependency chain."""
    registry = PhaseRegistry()
    
    def handler1():
        pass
    
    def handler2():
        pass
    
    def handler3():
        pass
    
    registry.register(PhaseDefinition("phase1", 1, [], handler1))
    registry.register(PhaseDefinition("phase2", 2, ["phase1"], handler2))
    registry.register(PhaseDefinition("phase3", 3, ["phase2"], handler3))
    
    order = registry.get_execution_order()
    assert order == ["phase1", "phase2", "phase3"]


def test_get_execution_order_parallel():
    """Test execution order with parallel phases."""
    registry = PhaseRegistry()
    
    def handler1():
        pass
    
    def handler2():
        pass
    
    def handler3():
        pass
    
    registry.register(PhaseDefinition("phase1", 1, [], handler1))
    registry.register(PhaseDefinition("phase2", 2, ["phase1"], handler2))
    registry.register(PhaseDefinition("phase3", 2, ["phase1"], handler3))
    
    order = registry.get_execution_order()
    # phase1 must come first, phase2 and phase3 can be in any order
    assert order[0] == "phase1"
    assert "phase2" in order
    assert "phase3" in order
    assert order.index("phase2") > order.index("phase1")
    assert order.index("phase3") > order.index("phase1")


def test_get_all_dependencies():
    """Test getting all dependencies recursively."""
    registry = PhaseRegistry()
    
    def handler():
        pass
    
    registry.register(PhaseDefinition("phase1", 1, [], handler))
    registry.register(PhaseDefinition("phase2", 2, ["phase1"], handler))
    registry.register(PhaseDefinition("phase3", 3, ["phase2"], handler))
    
    deps = registry.get_all_dependencies("phase3")
    assert "phase1" in deps
    assert "phase2" in deps


def test_validate_dependencies():
    """Test dependency validation."""
    registry = PhaseRegistry()
    
    def handler():
        pass
    
    registry.register(PhaseDefinition("phase1", 1, [], handler))
    registry.register(PhaseDefinition("phase2", 2, ["phase1", "nonexistent"], handler))
    
    errors = registry.validate_dependencies()
    assert len(errors) == 1
    assert "nonexistent" in errors[0]


def test_circular_dependency_detection():
    """Test that circular dependencies are detected."""
    registry = PhaseRegistry()
    
    def handler():
        pass
    
    registry.register(PhaseDefinition("phase1", 1, ["phase2"], handler))
    registry.register(PhaseDefinition("phase2", 2, ["phase1"], handler))
    
    with pytest.raises(ValueError, match="Circular dependency"):
        registry.get_execution_order()
