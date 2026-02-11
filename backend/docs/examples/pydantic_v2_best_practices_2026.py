"""Pydantic v2 Best Practices - Context7 Validated Examples

References:
- Library: /websites/pydantic_dev_2_12 (Score: 83.5/100)
- Documentation: https://docs.pydantic.dev/2.12

Key patterns demonstrated:
1. computed_field for derived properties
2. model_validator for complex validation
3. field_validator with @classmethod
4. model_config optimization
5. model_validate instead of parse_obj
6. Proper serialization patterns
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, model_validator


# ============================================================================
# 1. COMPUTED FIELDS (Context7 Best Practice)
# ============================================================================


class Rectangle(BaseModel):
    """Example: Using computed_field for derived properties

    Context7 Validation: Use @computed_field for properties that should be
    included in model serialization but computed from other fields.

    Benefits:
    - Included in model_dump() output
    - Included in JSON schema
    - No need to store redundant data
    """

    width: float = Field(..., gt=0, description="Rectangle width")
    length: float = Field(..., gt=0, description="Rectangle length")

    @computed_field
    @property
    def area(self) -> float:
        """Computed field: Area of rectangle

        Context7: Use @computed_field + @property for read-only computed values
        """
        return round(self.width * self.length, 2)

    @computed_field
    @property
    def perimeter(self) -> float:
        """Computed field: Perimeter of rectangle"""
        return round(2 * (self.width + self.length), 2)


# Example usage:
rect = Rectangle(width=10, length=5)
print(rect.model_dump())
# Output: {'width': 10, 'length': 5, 'area': 50.0, 'perimeter': 30.0}


# ============================================================================
# 2. MODEL VALIDATOR (Context7 Best Practice)
# ============================================================================


class UserRegistration(BaseModel):
    """Example: Using model_validator for complex cross-field validation

    Context7 Validation: Use @model_validator for validation that requires
    multiple fields or complex business logic.
    """

    username: str = Field(..., min_length=3, max_length=50)
    email: str
    password: str = Field(..., min_length=8)
    password_confirm: str

    @model_validator(mode="before")
    @classmethod
    def check_sensitive_fields(cls, data: Any) -> Any:
        """Validate before model instantiation

        Context7: mode='before' runs on raw input data before field validation
        Use for:
        - Removing sensitive fields
        - Normalizing input
        - Pre-processing data
        """
        if isinstance(data, dict):
            # Security: Don't allow card_number in registration
            if "card_number" in data:
                raise ValueError("'card_number' should not be included in registration")

            # Normalize email to lowercase
            if "email" in data:
                data["email"] = data["email"].lower().strip()

        return data

    @model_validator(mode="after")
    def check_passwords_match(self) -> "UserRegistration":
        """Validate after model instantiation

        Context7: mode='after' runs after all fields are validated
        Use for:
        - Cross-field validation
        - Business logic validation
        - Complex constraints
        """
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self

    model_config = {
        "str_strip_whitespace": True,  # Auto-strip whitespace from strings
        "validate_assignment": True,  # Validate on attribute assignment
    }


# Example usage:
try:
    user = UserRegistration(
        username="john_doe",
        email="  JOHN@EXAMPLE.COM  ",  # Will be normalized
        password="SecurePass123",
        password_confirm="SecurePass123",
    )
    print(user.model_dump())
    # Output: {'username': 'john_doe', 'email': 'john@example.com', ...}
except ValidationError as e:
    print(e)


# ============================================================================
# 3. FIELD VALIDATOR (Context7 Best Practice)
# ============================================================================


class Product(BaseModel):
    """Example: Using field_validator for single-field validation

    Context7: Use @field_validator for field-specific validation logic
    """

    name: str = Field(..., min_length=1)
    sku: str
    price: float = Field(..., gt=0)
    discount_percent: float = Field(default=0, ge=0, le=100)

    @field_validator("sku")
    @classmethod
    def validate_sku_format(cls, v: str) -> str:
        """Validate SKU format: XXX-NNNNNN

        Context7: @field_validator MUST be @classmethod in Pydantic v2
        """
        if not v.upper().match(r"^[A-Z]{3}-\d{6}$"):
            # Attempt to fix common issues
            v = v.upper().replace(" ", "").replace("_", "-")

        # Final validation
        import re

        if not re.match(r"^[A-Z]{3}-\d{6}$", v):
            raise ValueError("SKU must be in format: XXX-NNNNNN (e.g., ABC-123456)")

        return v

    @field_validator("discount_percent")
    @classmethod
    def validate_discount(cls, v: float, info) -> float:
        """Validate discount percentage

        Context7: Use info.data to access other field values
        """
        # Access price from info.data (already validated fields)
        price = info.data.get("price", 0)

        # Business rule: Discounts > 50% require price > $100
        if v > 50 and price < 100:
            raise ValueError("Discounts above 50% are only available for products over $100")

        return v

    @computed_field
    @property
    def final_price(self) -> float:
        """Computed field: Price after discount"""
        return round(self.price * (1 - self.discount_percent / 100), 2)


# ============================================================================
# 4. MODEL CONFIG OPTIMIZATION (Context7 Best Practice)
# ============================================================================


class OptimizedSettings(BaseModel):
    """Example: Optimized model_config for performance and features

    Context7 Validation: Configure model behavior for production use
    """

    api_key: str = Field(..., min_length=32)
    api_endpoint: str = Field(..., pattern=r"^https?://")
    timeout: int = Field(default=30, ge=1, le=300)
    retries: int = Field(default=3, ge=0, le=10)

    model_config = {
        # Performance optimizations
        "validate_assignment": True,  # Validate when setting attributes
        "validate_default": True,  # Validate default values
        "use_enum_values": True,  # Use enum values instead of enum instances
        "str_strip_whitespace": True,  # Auto-strip whitespace
        "str_to_lower": False,  # Don't lowercase strings automatically
        "str_to_upper": False,  # Don't uppercase strings automatically
        # ORM mode (for database models)
        "from_attributes": True,  # Pydantic v2 replacement for orm_mode
        # Serialization
        "populate_by_name": True,  # Allow population by field name or alias
        "json_encoders": {
            datetime: lambda v: v.isoformat(),  # Custom JSON encoding
        },
        # Schema generation
        "json_schema_extra": {
            "examples": [
                {
                    "api_key": "a" * 32,
                    "api_endpoint": "https://api.example.com",
                    "timeout": 30,
                    "retries": 3,
                }
            ]
        },
        # Validation behavior
        "strict": False,  # Allow type coercion
        "arbitrary_types_allowed": False,  # Disallow arbitrary types for safety
    }


# ============================================================================
# 5. MODEL VALIDATE (Context7 Best Practice)
# ============================================================================


class User(BaseModel):
    """Example: Using model_validate instead of parse_obj

    Context7: Pydantic v2 uses model_validate for parsing data
    """

    id: int
    name: str
    email: str

    model_config = {"from_attributes": True}


# OLD: Pydantic v1
# user = User.parse_obj({"id": 1, "name": "John", "email": "john@example.com"})

# NEW: Pydantic v2 (Context7 validated)
data_dict = {"id": 1, "name": "John", "email": "john@example.com"}
user = User.model_validate(data_dict)

# ORM-like object example
class ORMObject:
    def __init__(self, id: int, name: str, email: str):
        self.id = id
        self.name = name
        self.email = email


orm_obj = ORMObject(id=2, name="Jane", email="jane@example.com")
user_from_orm = User.model_validate(orm_obj)

print(user_from_orm.model_dump())
# Output: {'id': 2, 'name': 'Jane', 'email': 'jane@example.com'}


# ============================================================================
# 6. ADVANCED: DYNAMIC MODEL CREATION (Context7)
# ============================================================================


from pydantic import create_model


def create_dynamic_user_model(role: str):
    """Create dynamic Pydantic model based on role

    Context7: Use create_model for runtime model generation
    """
    # Base fields for all roles
    base_fields = {
        "username": (str, Field(..., min_length=3)),
        "email": (str, ...),
    }

    # Add role-specific fields
    if role == "admin":
        base_fields["admin_level"] = (int, Field(default=1, ge=1, le=5))
    elif role == "customer":
        base_fields["customer_id"] = (str, ...)

    # Add validators
    def validate_username(cls, v):
        assert v.isalnum(), "Username must be alphanumeric"
        return v

    validators = {
        "username_validator": field_validator("username")(validate_username),
    }

    # Create model dynamically
    DynamicUserModel = create_model(
        f"{role.capitalize()}User",
        __base__=BaseModel,
        __validators__=validators,
        **base_fields,
    )

    return DynamicUserModel


# Example usage:
AdminUser = create_dynamic_user_model("admin")
admin = AdminUser(username="admin123", email="admin@example.com", admin_level=5)
print(admin.model_dump())


# ============================================================================
# 7. SERIALIZATION PATTERNS (Context7 Best Practice)
# ============================================================================


class CompleteExample(BaseModel):
    """Complete example with all Context7 best practices"""

    # Field definitions with validation
    id: int = Field(..., gt=0, description="Unique identifier")
    created_at: datetime = Field(default_factory=datetime.now)
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    age: int | None = Field(None, ge=0, le=150)  # Python 3.10+ union syntax
    tags: list[str] = Field(default_factory=list)

    # Computed fields
    @computed_field
    @property
    def display_name(self) -> str:
        """Computed display name"""
        return f"{self.name} (ID: {self.id})"

    # Field validators
    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Ensure tags are unique and lowercase"""
        return list(set(tag.lower() for tag in v))

    # Model validators
    @model_validator(mode="after")
    def validate_model(self) -> "CompleteExample":
        """Complex model validation"""
        # Business rule: Users under 18 must have parental consent tag
        if self.age and self.age < 18:
            if "parental_consent" not in self.tags:
                raise ValueError("Users under 18 must have 'parental_consent' tag")
        return self

    # Model config
    model_config = {
        "validate_assignment": True,
        "from_attributes": True,
        "str_strip_whitespace": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "name": "John Doe",
                    "email": "john@example.com",
                    "age": 25,
                    "tags": ["premium", "verified"],
                }
            ]
        },
    }

    # Serialization methods
    def model_dump_public(self) -> dict:
        """Custom serialization excluding sensitive fields

        Context7: Create custom serialization methods for different use cases
        """
        data = self.model_dump()
        # Remove internal fields
        data.pop("id", None)
        data.pop("created_at", None)
        return data


# ============================================================================
# MIGRATION GUIDE: Pydantic v1 → v2
# ============================================================================

"""
PYDANTIC V1 (OLD):
──────────────────
class User(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True

    @validator('name')
    def validate_name(cls, v):
        return v.strip()

user = User.parse_obj(data)
json_data = user.dict()


PYDANTIC V2 (NEW - Context7 Validated):
────────────────────────────────────────
class User(BaseModel):
    id: int
    name: str

    model_config = {
        'from_attributes': True,  # Replaces orm_mode
    }

    @field_validator('name')
    @classmethod  # MUST be classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()

user = User.model_validate(data)  # Replaces parse_obj
json_data = user.model_dump()     # Replaces dict()


BENEFITS:
✅ Better type safety
✅ Faster performance (5-50x in some cases)
✅ Clearer API surface
✅ Better JSON schema generation
✅ Improved error messages
"""


# ============================================================================
# PERFORMANCE TIPS (Context7 Validated)
# ============================================================================

"""
1. Use model_validate instead of model_validate_json when data is already dict
   ✅ FAST: User.model_validate(dict_data)
   ❌ SLOW: User.model_validate_json(json.dumps(dict_data))

2. Disable validation for trusted data
   ✅ FAST: User.model_construct(**trusted_data)  # Skip validation
   ⚠️  Use only for data from trusted sources (database, internal APIs)

3. Use computed_field instead of recalculating values
   ✅ FAST: @computed_field with @functools.cached_property
   ❌ SLOW: Recalculating in every method call

4. Batch validation for large datasets
   ✅ FAST: [User.model_validate(row) for row in rows]
   ❌ SLOW: Individual validation in separate calls

5. Use model_config = {'frozen': True} for immutable models
   ✅ Performance boost + safety for cache keys
"""
